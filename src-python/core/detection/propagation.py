"""Cross-page PII propagation.

Ensures every detected PII text is flagged on *every* page where it
appears, not just the page where it was first detected.

Performance optimisations (X1/X2):
- Block offsets are computed once per page and cached.
- The ``covered`` overlap check uses a per-page sorted interval list
  with binary search instead of a global linear scan.
"""

from __future__ import annotations

import bisect
import logging
import re as _re
import unicodedata
import uuid
from collections import defaultdict

from core.detection.bbox_utils import _resolve_bbox_overlaps
from core.detection import detection_config as det_cfg
from core.detection.block_offsets import (
    _clamp_bbox,
    _compute_block_offsets,
    _char_offset_to_bbox,
    _char_offsets_to_line_bboxes,
)
from core.detection.noise_filters import (
    _is_loc_pipeline_noise,
    _is_org_pipeline_noise,
    _is_person_pipeline_noise,
    has_legal_suffix,
    _STRUCTURED_MIN_DIGITS,
)
from core.text_utils import strip_accents as _strip_accents, ws_collapse as _ws_collapse
from models.schemas import (
    PIIRegion,
    PIIType,
    PageData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Accent-agnostic helpers & whitespace collapse — imported from core.text_utils
# (_strip_accents, _ws_collapse)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tuning constants (see detection_config.py for documentation)
# ---------------------------------------------------------------------------
_PROPAGATION_OVERLAP_RATIO = det_cfg.PROPAGATION_OVERLAP_RATIO
_PROPAGATION_CONF_FACTOR = det_cfg.PROPAGATION_CONF_FACTOR
_MIN_BBOX_DIMENSION = det_cfg.MIN_BBOX_DIMENSION


# Characters treated as transparent for entity matching —
# various quotation marks that wrap entity names in running text.
_QUOTE_CHARS = frozenset(
    '"\'\'\u2018\u2019\u201A\u201B'   # single quotes / apostrophes
    '\u201C\u201D\u201E\u201F'         # double quotes
    '\u00AB\u00BB'                     # «»
    '\u2039\u203A'                     # ‹›
    '\u300C\u300D\u300E\u300F'         # CJK brackets
)


def _strip_quotes(text: str) -> str:
    """Remove quotation mark characters from *text*."""
    return ''.join(ch for ch in text if ch not in _QUOTE_CHARS)


def _neutralise_quotes(text: str) -> str:
    """Replace quotation mark characters with spaces (preserves string length)."""
    return ''.join(' ' if ch in _QUOTE_CHARS else ch for ch in text)


def _build_flex_pattern(norm_key: str) -> _re.Pattern:
    """Build a case-insensitive, whitespace-flexible regex for *norm_key*.

    Spaces in *norm_key* become ``\\s+`` so that the pattern matches
    regardless of whether the page text uses spaces, newlines, or other
    whitespace between words.

    Boundary assertions are chosen based on the first/last character of
    the key:

    * **Word character** (letter, digit, ``_``): use ``\\b`` — the
      standard word boundary that requires a transition between word and
      non-word characters.
    * **Non-word character** (period, parenthesis, …): use
      ``(?<!\\w)`` / ``(?!\\w)`` — zero-width assertions that simply
      require the adjacent character not to be a word character.  This
      avoids the classic ``\\b`` pitfall where a trailing period (e.g.
      ``inc.``, ``S.A.``) is followed by whitespace or end-of-string
      (both non-word), causing ``\\b`` to silently fail.
    """
    escaped = _re.escape(norm_key)
    # re.escape also escapes spaces (\ + space) — replace with \s+
    pat_str = escaped.replace('\\ ', r'\s+')

    # Leading boundary
    if norm_key and norm_key[0].isalnum():
        pat_str = r'\b' + pat_str
    else:
        pat_str = r'(?<!\w)' + pat_str

    # Trailing boundary
    if norm_key and norm_key[-1].isalnum():
        pat_str = pat_str + r'\b'
    else:
        pat_str = pat_str + r'(?!\w)'

    return _re.compile(pat_str, _re.IGNORECASE)


# ---------------------------------------------------------------------------
# Per-page interval tracker — O(log n) overlap check via binary search
# ---------------------------------------------------------------------------

class _PageIntervals:
    """Maintain sorted, non-overlapping intervals per page for fast overlap checks."""

    __slots__ = ("_starts", "_ends")

    def __init__(self) -> None:
        self._starts: list[int] = []
        self._ends: list[int] = []

    def has_overlap(self, cs: int, ce: int, min_ratio: float = _PROPAGATION_OVERLAP_RATIO) -> bool:
        """Return True if an existing interval overlaps [cs, ce) by >= min_ratio.

        Uses binary search on sorted start positions — O(log n).
        """
        threshold = min_ratio * (ce - cs)
        # Find candidate intervals that could overlap [cs, ce).
        # An interval (s, e) overlaps [cs, ce) iff s < ce AND e > cs.
        # idx = first position where _starts[idx] >= ce  →  all intervals
        # with index < idx have start < ce (necessary condition for overlap).
        idx = bisect.bisect_left(self._starts, ce)
        # Walk backwards from idx to find intervals that also satisfy e > cs.
        for i in range(idx - 1, -1, -1):
            if self._ends[i] <= cs:
                # This interval ends before our query starts.
                # Since starts are sorted but ends are NOT monotone, we
                # cannot safely break early — a wider interval with an
                # earlier start could still overlap.  Continue scanning.
                continue
            ov_start = max(cs, self._starts[i])
            ov_end = min(ce, self._ends[i])
            if ov_end - ov_start >= threshold:
                return True
        return False

    def add(self, cs: int, ce: int) -> None:
        """Insert interval [cs, ce) maintaining sorted order by start."""
        idx = bisect.bisect_left(self._starts, cs)
        self._starts.insert(idx, cs)
        self._ends.insert(idx, ce)


def propagate_regions_across_pages(
    regions: list[PIIRegion],
    pages: list[PageData],
) -> list[PIIRegion]:
    """Ensure every detected PII text is flagged on *every* page.

    For each unique PII text in *regions*, search all pages for
    additional occurrences and create new regions with properly-computed
    bounding boxes.

    Returns the full region list (originals + propagated).
    """
    if not regions or not pages:
        return regions

    page_map: dict[int, PageData] = {p.page_number: p for p in pages}

    # Collect unique PII texts and their best template
    text_to_template: dict[str, PIIRegion] = {}
    for r in regions:
        key = r.text.strip()
        if not key or len(key) < 2:
            continue
        if r.pii_type == PIIType.ORG and (
            key.isdigit()
            or (key and key[0].isdigit() and not has_legal_suffix(key))
            or len(key) <= 2
        ):
            continue
        if r.pii_type == PIIType.LOCATION and _is_loc_pipeline_noise(key):
            continue
        if r.pii_type == PIIType.PERSON and _is_person_pipeline_noise(key):
            continue
        _min_prop = _STRUCTURED_MIN_DIGITS.get(r.pii_type)
        if _min_prop is not None:
            digs = sum(c.isdigit() for c in key)
            if digs < _min_prop:
                continue
            if r.pii_type == PIIType.SSN and any(c in key for c in '$€£'):
                continue
        # Accent-agnostic, case-insensitive, whitespace-normalised keying
        # Also neutralise quotation marks (→ spaces) so L'ESPRIT keys
        # consistently with the per-page search which also neutralises quotes.
        norm_key = _ws_collapse(_strip_accents(_neutralise_quotes(key))).lower()
        existing = text_to_template.get(norm_key)
        if existing is None or r.confidence > existing.confidence:
            text_to_template[norm_key] = r

    if not text_to_template:
        logger.debug("Propagation: no propagatable PII texts found")
        return regions

    # X2: Per-page interval index for O(log n) overlap check
    page_intervals: dict[int, _PageIntervals] = defaultdict(_PageIntervals)
    for r in regions:
        page_intervals[r.page_number].add(r.char_start, r.char_end)

    # X1: Cache block offsets per page (computed once, reused for all texts)
    block_offsets_cache: dict[int, list] = {}
    # Cache accent-stripped full_text per page for accent-agnostic search
    norm_full_cache: dict[int, str] = {}

    propagated: list[PIIRegion] = []

    for norm_pii_text, template in text_to_template.items():
        # Whitespace-flexible, case-insensitive regex for this key
        _pat = _build_flex_pattern(norm_pii_text)

        for page_data in pages:
            full_text = page_data.full_text
            if not full_text:
                continue

            pn = page_data.page_number
            intervals = page_intervals[pn]

            # Accent-agnostic search: compare stripped versions
            if pn not in norm_full_cache:
                norm_full_cache[pn] = _neutralise_quotes(_strip_accents(full_text))
            norm_full = norm_full_cache[pn]

            for _m in _pat.finditer(norm_full):
                char_start = _m.start()
                char_end = _m.end()

                if intervals.has_overlap(char_start, char_end, 0.5):
                    continue

                # X1: Get cached block offsets for this page
                if pn not in block_offsets_cache:
                    block_offsets_cache[pn] = _compute_block_offsets(
                        page_data.text_blocks, full_text,
                    )
                block_offsets = block_offsets_cache[pn]

                line_bboxes = _char_offsets_to_line_bboxes(
                    char_start, char_end, block_offsets,
                )
                if not line_bboxes:
                    bbox = _char_offset_to_bbox(char_start, char_end, block_offsets)
                    if bbox is None:
                        continue
                    line_bboxes = [bbox]

                for bbox in line_bboxes:
                    clamped = _clamp_bbox(bbox, page_data.width, page_data.height)
                    if clamped.x1 - clamped.x0 < _MIN_BBOX_DIMENSION or clamped.y1 - clamped.y0 < _MIN_BBOX_DIMENSION:
                        continue
                    new_region = PIIRegion(
                        id=uuid.uuid4().hex[:12],
                        page_number=page_data.page_number,
                        bbox=clamped,
                        text=full_text[char_start:char_end],
                        pii_type=template.pii_type,
                        confidence=template.confidence,
                        source=template.source,
                        char_start=char_start,
                        char_end=char_end,
                        action=template.action,
                    )
                    propagated.append(new_region)
                intervals.add(char_start, char_end)

    if propagated:
        logger.info(
            "Propagated %d additional regions across %d pages from %d unique PII texts",
            len(propagated), len(pages), len(text_to_template),
        )

    all_regions = regions + propagated

    # Final overlap resolution per page
    result: list[PIIRegion] = []
    pages_with_regions: set[int] = {r.page_number for r in all_regions}
    for pn in sorted(pages_with_regions):
        page_regions = [r for r in all_regions if r.page_number == pn]
        result.extend(_resolve_bbox_overlaps(page_regions))

    # Clamp every region to its page bounds 
    clamped_result: list[PIIRegion] = []
    for r in result:
        pd = page_map.get(r.page_number)
        if pd is None:
            clamped_result.append(r)
            continue
        cb = _clamp_bbox(r.bbox, pd.width, pd.height)
        if cb.x1 - cb.x0 < _MIN_BBOX_DIMENSION or cb.y1 - cb.y0 < _MIN_BBOX_DIMENSION:
            continue
        if cb != r.bbox:
            r = r.model_copy(update={"bbox": cb})
        clamped_result.append(r)

    return clamped_result


# ---------------------------------------------------------------------------
# Partial ORG name propagation
# ---------------------------------------------------------------------------

def _generate_contiguous_subphrases(words: list[str], min_words: int = 2) -> list[str]:
    """Return all contiguous sub-phrases of *words* with >= *min_words* words.

    Excludes the full phrase itself (already handled by exact propagation).
    """
    n = len(words)
    subphrases: list[str] = []
    for length in range(min_words, n):          # skip n (the full phrase)
        for start in range(n - length + 1):
            subphrases.append(" ".join(words[start : start + length]))
    return subphrases


def propagate_partial_org_names(
    regions: list[PIIRegion],
    pages: list[PageData],
) -> list[PIIRegion]:
    """Find 2+-word sub-phrases of detected ORG names in every page.

    When "Deutsche Bank AG" has been detected, this function also flags
    occurrences of "Deutsche Bank" (2+ contiguous words from the original).

    * Only ORG regions with 3+ words are used as sources.
    * Sub-phrases that are noise (common dictionary words only, no legal
      suffix) are skipped.
    * New regions are created with confidence reduced by 15 %.
    * Existing regions are never duplicated (overlap check).
    """
    if not regions or not pages:
        return regions

    # 1. Collect unique multi-word ORG texts (accent-agnostic keying)
    org_texts: dict[str, PIIRegion] = {}
    for r in regions:
        if r.pii_type != PIIType.ORG:
            continue
        key = r.text.strip()
        words = key.split()
        if len(words) < 3:
            continue
        norm_key = _ws_collapse(_strip_accents(_neutralise_quotes(key))).lower()
        existing = org_texts.get(norm_key)
        if existing is None or r.confidence > existing.confidence:
            org_texts[norm_key] = r

    if not org_texts:
        return regions

    # 2. Build sub-phrase → template mapping (best parent confidence wins)
    #    Since these are derived from *confirmed* ORG names, we use a lighter
    #    filter than _is_org_pipeline_noise: only skip sub-phrases composed
    #    entirely of function words (articles, prepositions, conjunctions).
    _FUNCTION_WORDS: frozenset[str] = frozenset({
        # English
        "the", "a", "an", "of", "and", "or", "for", "in", "on", "at", "to",
        "by", "with", "from", "as", "is", "are", "was", "were",
        # French
        "le", "la", "les", "de", "du", "des", "et", "ou", "en", "au", "aux",
        "un", "une", "sur", "dans", "pour", "par", "avec",
        # German
        "der", "die", "das", "den", "dem", "des", "und", "oder", "für", "fuer",
        "mit", "von", "zu", "auf", "ein", "eine", "am", "im", "an", "bei",
        "aus", "nach", "über", "ueber",
        # Spanish
        "el", "los", "las", "del", "y", "o", "para", "con", "por",
        "al", "una", "uno",
        # Italian
        "il", "lo", "gli", "della", "dello", "dei", "degli", "delle", "e",
        "di", "da", "al", "alla", "alle", "ai", "nel", "nella",
        "sul", "sulla", "dal", "dalla",
        # Dutch
        "het", "een", "van", "voor", "met", "op", "te", "bij", "uit",
        # Portuguese
        "o", "os", "do", "da", "dos", "das", "com", "em", "no", "na",
        "nos", "nas", "ao", "aos", "um", "uma",
    })
    _NORM_FUNCTION_WORDS = frozenset(_strip_accents(w) for w in _FUNCTION_WORDS)

    sub_to_template: dict[str, PIIRegion] = {}
    for org_text, template in org_texts.items():
        words = org_text.split()
        for sub in _generate_contiguous_subphrases(words, min_words=2):
            # Skip sub-phrases made entirely of function words
            sub_words = sub.split()   # already lowercased
            if all(w in _NORM_FUNCTION_WORDS for w in sub_words):
                continue
            existing = sub_to_template.get(sub)
            if existing is None or template.confidence > existing.confidence:
                sub_to_template[sub] = template

    # Remove sub-phrases that are already exact-match regions (any type)
    existing_texts: set[str] = {
        _ws_collapse(_strip_accents(_neutralise_quotes(r.text.strip()))).lower()
        for r in regions
    }
    for txt in list(sub_to_template):
        if txt in existing_texts:
            del sub_to_template[txt]

    if not sub_to_template:
        return regions

    # 3a. Retype existing LOCATION/PERSON regions that match an ORG sub-phrase
    #     or the full ORG name itself.
    #     NER may independently tag part of a known ORG name as LOCATION
    #     (e.g. "der Alten Försterei" from "An der Alten Försterei" Stadionbetriebs AG).
    #     Those should be ORG, not LOCATION.
    _retype_lookup: dict[str, PIIRegion] = {**sub_to_template}
    # Also include full ORG names so they get retyped too
    for k, v in org_texts.items():
        if k not in _retype_lookup:
            _retype_lookup[k] = v

    _retyped = 0
    for i, r in enumerate(regions):
        if r.pii_type not in (PIIType.LOCATION, PIIType.PERSON):
            continue
        r_norm = _ws_collapse(_strip_accents(_neutralise_quotes(r.text.strip()))).lower()
        tpl = _retype_lookup.get(r_norm)
        if tpl is not None:
            regions[i] = r.model_copy(update={
                "pii_type": PIIType.ORG,
                "confidence": max(r.confidence, round(tpl.confidence * _PROPAGATION_CONF_FACTOR, 4)),
            })
            _retyped += 1
    if _retyped:
        logger.info(
            "Partial-ORG propagation: retyped %d LOCATION/PERSON region(s) to ORG "
            "(sub-phrases of known ORG names)",
            _retyped,
        )

    # 3b. Build per-page interval index from existing regions
    page_intervals: dict[int, _PageIntervals] = defaultdict(_PageIntervals)
    for r in regions:
        page_intervals[r.page_number].add(r.char_start, r.char_end)

    # Block-offset cache
    block_offsets_cache: dict[int, list] = {}
    # Cache accent-stripped full_text per page
    norm_full_cache: dict[int, str] = {}

    propagated: list[PIIRegion] = []

    # Process longer sub-phrases first so they claim intervals before
    # shorter overlapping ones.
    sorted_subs = sorted(sub_to_template.items(), key=lambda kv: -len(kv[0]))

    for sub_text, template in sorted_subs:
        conf = round(template.confidence * _PROPAGATION_CONF_FACTOR, 4)
        # Whitespace-flexible, case-insensitive regex with word boundaries
        _sub_pat = _build_flex_pattern(sub_text)

        for page_data in pages:
            full_text = page_data.full_text
            if not full_text:
                continue

            pn = page_data.page_number
            intervals = page_intervals[pn]

            # Accent-agnostic search
            if pn not in norm_full_cache:
                norm_full_cache[pn] = _neutralise_quotes(_strip_accents(full_text))
            norm_full = norm_full_cache[pn]

            for _m in _sub_pat.finditer(norm_full):
                char_start = _m.start()
                char_end = _m.end()

                # Require word boundaries to avoid matching inside words
                if char_start > 0 and full_text[char_start - 1].isalnum():
                    continue
                if char_end < len(full_text) and full_text[char_end].isalnum():
                    continue

                if intervals.has_overlap(char_start, char_end, _PROPAGATION_OVERLAP_RATIO):
                    continue

                # Compute bbox
                if pn not in block_offsets_cache:
                    block_offsets_cache[pn] = _compute_block_offsets(
                        page_data.text_blocks, full_text,
                    )
                block_offsets = block_offsets_cache[pn]

                line_bboxes = _char_offsets_to_line_bboxes(
                    char_start, char_end, block_offsets,
                )
                if not line_bboxes:
                    bbox = _char_offset_to_bbox(char_start, char_end, block_offsets)
                    if bbox is None:
                        continue
                    line_bboxes = [bbox]

                for bbox in line_bboxes:
                    clamped = _clamp_bbox(bbox, page_data.width, page_data.height)
                    if clamped.x1 - clamped.x0 < _MIN_BBOX_DIMENSION or clamped.y1 - clamped.y0 < _MIN_BBOX_DIMENSION:
                        continue
                    new_region = PIIRegion(
                        id=uuid.uuid4().hex[:12],
                        page_number=page_data.page_number,
                        bbox=clamped,
                        text=full_text[char_start:char_end],
                        pii_type=PIIType.ORG,
                        confidence=conf,
                        source=template.source,
                        char_start=char_start,
                        char_end=char_end,
                        action=template.action,
                    )
                    propagated.append(new_region)
                intervals.add(char_start, char_end)

    if propagated:
        logger.info(
            "Partial-ORG propagation: added %d regions from %d sub-phrases of %d ORG names",
            len(propagated), len(sub_to_template), len(org_texts),
        )

    if not propagated:
        return regions

    all_regions = regions + propagated

    # Overlap resolution + clamping (same as main propagation)
    page_map: dict[int, PageData] = {p.page_number: p for p in pages}
    result: list[PIIRegion] = []
    pages_with_regions: set[int] = {r.page_number for r in all_regions}
    for pn in sorted(pages_with_regions):
        page_regions = [r for r in all_regions if r.page_number == pn]
        result.extend(_resolve_bbox_overlaps(page_regions))

    clamped_result: list[PIIRegion] = []
    for r in result:
        pd = page_map.get(r.page_number)
        if pd is None:
            clamped_result.append(r)
            continue
        cb = _clamp_bbox(r.bbox, pd.width, pd.height)
        if cb.x1 - cb.x0 < _MIN_BBOX_DIMENSION or cb.y1 - cb.y0 < _MIN_BBOX_DIMENSION:
            continue
        if cb != r.bbox:
            r = r.model_copy(update={"bbox": cb})
        clamped_result.append(r)

    return clamped_result
