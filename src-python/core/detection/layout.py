"""Page layout analysis: column band detection and detection-text construction.

Builds a *detection text* that joins consecutive lines within each column
with a space (instead of \\n), allowing NER / GLiNER to recognise entity
names that span two visual lines.

The parallel ``dt_to_ft`` offset map translates any match position found
in the detection text back to the corresponding position in the stored
``full_text``, so all downstream code (bbox lookup, PIIRegion char offsets)
stays unmodified.

Column model
-----------
A page is divided into vertical x-bands called *column bands*.  Within each
band, lines are stacked top-to-bottom.  Two complementary signals drive
column detection:

1. **x-gap** — a horizontal gap within a visual line exceeding
   ``_COL_GAP_LINE_RATIO × avg_word_height`` is a candidate column gutter.
2. **left-alignment** — words to the right of a confirmed gutter must have
   tightly clustered x0 values (low std-dev); this is the typographic
   invariant of any left-aligned column and is the primary validation signal.

A gap is *confirmed* when it appears on at least ``_COL_MIN_LINE_VOTES``
distinct page lines.  Single-occurrence wide gaps (one long word, missing
text) are ignored.

One-line columns are a natural degenerate case and require no special
handling — a column with a single line is processed identically to one with
many lines.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import NamedTuple

from models.schemas import PageData, TextBlock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# A horizontal gap within a visual line must exceed this multiple of the
# average word height to be a candidate column gutter.
_COL_GAP_LINE_RATIO: float = 2.5

# A candidate gap is confirmed only when >= this many distinct page lines
# show a gap at approximately the same x position.
_COL_MIN_LINE_VOTES: int = 2

# Left-alignment quality threshold.  The std-dev of x0 values for the words
# immediately to the right of a candidate gutter must be ≤
# avg_word_height × _COL_LEFT_ALIGN_STD_RATIO for the gap to be validated.
_COL_LEFT_ALIGN_STD_RATIO: float = 0.6

# Gap vote positions within this many PDF points are merged into one cluster.
_COL_GAP_MERGE_TOLERANCE: float = 12.0

# Two consecutive lines in the same column are joined with a SPACE when
# their y-gap is ≤ this multiple of the average word height.  Larger
# gaps produce a \\n (paragraph / section break within the column).
_COL_LINE_JOIN_RATIO: float = 2.0

# Words whose x-width exceeds this fraction of page width are treated as
# full-width headings and excluded from column gap analysis (but are still
# assigned to the nearest column band after bands are finalized).
_FULL_WIDTH_RATIO: float = 0.55

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ColumnBand:
    """A vertical x-band representing one logical column on the page."""

    x_left: float   # inclusive left boundary (PDF pts)
    x_right: float  # inclusive right boundary (PDF pts)
    blocks: list[TextBlock] = field(default_factory=list)


class OffsetMap(NamedTuple):
    """Result of :func:`build_detection_text`.

    ``dt_to_ft[i]`` is the position in ``full_text`` that produced
    ``detection_text[i]``, or ``-1`` for separator characters inserted by
    the layout assembler (spaces or newlines that do not exist in
    ``full_text``).
    """

    detection_text: str
    dt_to_ft: list[int]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _avg_word_height(blocks: list[TextBlock]) -> float:
    if not blocks:
        return 10.0
    return sum(b.bbox.y1 - b.bbox.y0 for b in blocks) / len(blocks)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


# ---------------------------------------------------------------------------
# Column band detection
# ---------------------------------------------------------------------------


def detect_column_bands(
    text_blocks: list[TextBlock],
    page_width: float,
) -> list[ColumnBand]:
    """Detect column x-bands from word positions.

    Uses two complementary signals:

    1. **x-gap**: a horizontal gap between consecutive words on the same
       visual line that exceeds ``_COL_GAP_LINE_RATIO × avg_word_height``
       is a candidate column gutter.  The gap's *x-midpoint* casts a vote.

    2. **left-alignment**: once candidate gutters are established, words
       immediately to the right of a gutter are expected to share a tight
       left edge (low std-dev of x0).  Gutters whose right-side words are
       scattered are rejected.

    Returns a list of :class:`ColumnBand` objects sorted left-to-right,
    each with ``.blocks`` populated.  Always returns at least one band.
    """
    from core.ingestion.loader import _cluster_into_lines

    if not text_blocks:
        return []

    # Exclude full-width spans (titles, horizontal rules) from gap analysis.
    # They are put back into bands after the bands are established.
    col_blocks = [
        b for b in text_blocks
        if (b.bbox.x1 - b.bbox.x0) <= page_width * _FULL_WIDTH_RATIO
    ] or text_blocks  # if everything is wide, treat as single column

    avg_h = _avg_word_height(col_blocks)
    gap_threshold = max(avg_h * _COL_GAP_LINE_RATIO, 15.0)

    lines = _cluster_into_lines(col_blocks)

    # ── Pass 1: collect gap x-midpoint votes ──────────────────────────
    gap_votes: list[float] = []
    for line_blocks in lines:
        if len(line_blocks) < 2:
            continue
        for i in range(1, len(line_blocks)):
            prev = line_blocks[i - 1]
            curr = line_blocks[i]
            gap = curr.bbox.x0 - prev.bbox.x1
            if gap >= gap_threshold:
                gap_votes.append((prev.bbox.x1 + curr.bbox.x0) / 2.0)

    def _single_band() -> list[ColumnBand]:
        band = ColumnBand(
            x_left=min(b.bbox.x0 for b in col_blocks),
            x_right=max(b.bbox.x1 for b in col_blocks),
        )
        band.blocks = list(text_blocks)
        return [band]

    if not gap_votes:
        return _single_band()

    # ── Pass 2: cluster votes by x-position ───────────────────────────
    gap_votes.sort()
    clusters: list[list[float]] = [[gap_votes[0]]]
    for gx in gap_votes[1:]:
        if gx - clusters[-1][-1] <= _COL_GAP_MERGE_TOLERANCE:
            clusters[-1].append(gx)
        else:
            clusters.append([gx])

    confirmed_gaps: list[float] = [
        sum(c) / len(c)
        for c in clusters
        if len(c) >= _COL_MIN_LINE_VOTES
    ]

    if not confirmed_gaps:
        return _single_band()

    # ── Pass 3: validate with left-alignment score ─────────────────────
    # Words whose x0 is just to the right of the gap centre (within a
    # plausible column-indent window) form the "right of gap" population.
    # Tight clustering (low std-dev) confirms a genuine column left-edge.
    validated_gaps: list[float] = []
    for gx in confirmed_gaps:
        right_x0 = [
            b.bbox.x0
            for b in col_blocks
            if gx - 5.0 < b.bbox.x0 <= gx + avg_h * 4.0
        ]
        if len(right_x0) < 2:
            validated_gaps.append(gx)  # too few data points → keep conservatively
            continue
        std = _std(right_x0)
        align_score = 1.0 / (1.0 + std)
        needed_score = 1.0 / (1.0 + avg_h * _COL_LEFT_ALIGN_STD_RATIO)
        if align_score >= needed_score:
            validated_gaps.append(gx)
            logger.debug(
                "Column gap x=%.1f ✓  right_x0_std=%.2f align=%.3f",
                gx, std, align_score,
            )
        else:
            logger.debug(
                "Column gap x=%.1f ✗  right_x0_std=%.2f (scattered)",
                gx, std,
            )

    if not validated_gaps:
        return _single_band()

    # ── Build ColumnBand objects from validated gap boundaries ─────────
    bounds = [0.0] + sorted(validated_gaps) + [page_width]
    bands: list[ColumnBand] = [
        ColumnBand(x_left=bounds[i], x_right=bounds[i + 1])
        for i in range(len(bounds) - 1)
    ]

    # Assign every block (including full-width ones) to the band whose
    # x-range contains the block's horizontal centre.
    for block in text_blocks:
        cx = (block.bbox.x0 + block.bbox.x1) / 2.0
        assigned = False
        for band in bands:
            if band.x_left <= cx <= band.x_right:
                band.blocks.append(block)
                assigned = True
                break
        if not assigned:
            # Nearest band by distance from centre to band boundaries
            nearest = min(
                bands,
                key=lambda b: min(abs(cx - b.x_left), abs(cx - b.x_right)),
            )
            nearest.blocks.append(block)

    bands = [b for b in bands if b.blocks]
    logger.debug(
        "Page column layout: %d band(s) — %s",
        len(bands),
        " | ".join(
            f"x[{b.x_left:.0f}–{b.x_right:.0f}] {len(b.blocks)}w"
            for b in bands
        ),
    )
    return bands


# ---------------------------------------------------------------------------
# Detection-text construction
# ---------------------------------------------------------------------------


def build_detection_text(
    page_data: PageData,
    block_offsets: list[tuple[int, int, "TextBlock"]],
) -> OffsetMap:
    """Build a detection text that joins cross-line content within columns.

    Within each column, two consecutive lines whose y-gap is ≤
    ``_COL_LINE_JOIN_RATIO × avg_word_height`` are joined with a **space**
    instead of a newline.  This is the key change that lets NER / GLiNER
    recognise entity names split across two visual lines.

    Paragraph breaks (large y-gaps within a column) and column boundaries
    still produce newlines, preserving sentence context for other entity
    types.

    ``block_offsets`` is the output of
    ``_compute_block_offsets(page_data.text_blocks, page_data.full_text)``.

    Returns an :class:`OffsetMap` with ``detection_text`` and a parallel
    ``dt_to_ft`` list mapping each character position in ``detection_text``
    to the corresponding position in ``page_data.full_text``, or ``-1`` for
    inserted separator characters.
    """
    from core.ingestion.loader import _cluster_into_lines

    text_blocks = page_data.text_blocks
    full_text = page_data.full_text
    page_width = page_data.width

    if not text_blocks or not full_text:
        return OffsetMap(full_text, list(range(len(full_text))))

    # Build block → (ft_start, ft_end) lookup keyed by object id.
    # Object ids are stable within a single call stack.
    block_ft: dict[int, tuple[int, int]] = {
        id(blk): (fs, fe) for fs, fe, blk in block_offsets
    }

    avg_h = _avg_word_height(text_blocks)
    bands = detect_column_bands(text_blocks, page_width)

    dt_chars: list[str] = []
    dt_to_ft: list[int] = []

    def _append_block(block: TextBlock) -> None:
        """Append word characters tracking their full_text positions."""
        bid = id(block)
        if bid in block_ft:
            ft_start, _ = block_ft[bid]
            for ci, ch in enumerate(block.text):
                dt_chars.append(ch)
                dt_to_ft.append(ft_start + ci)
        else:
            # Block not found in offsets (shouldn't happen) — use sentinel
            for ch in block.text:
                dt_chars.append(ch)
                dt_to_ft.append(-1)

    def _sep(ch: str) -> None:
        dt_chars.append(ch)
        dt_to_ft.append(-1)

    for band_idx, band in enumerate(bands):
        if band_idx > 0:
            _sep("\n")  # column boundary

        if not band.blocks:
            continue

        lines = _cluster_into_lines(band.blocks)
        prev_line_bottom: float | None = None

        for line_blocks in lines:
            line_top = min(b.bbox.y0 for b in line_blocks)
            line_bottom = max(b.bbox.y1 for b in line_blocks)

            if prev_line_bottom is not None:
                y_gap = line_top - prev_line_bottom
                if y_gap > avg_h * _COL_LINE_JOIN_RATIO:
                    _sep("\n")   # paragraph break — preserve sentence boundary
                else:
                    _sep(" ")   # ← KEY: enables cross-line NER recognition

            for word_idx, block in enumerate(line_blocks):
                if word_idx > 0:
                    _sep(" ")
                _append_block(block)

            prev_line_bottom = line_bottom

    detection_text = "".join(dt_chars)
    return OffsetMap(detection_text=detection_text, dt_to_ft=dt_to_ft)


# ---------------------------------------------------------------------------
# Match translation
# ---------------------------------------------------------------------------


def translate_match(match, dt_to_ft: list[int], full_text: str):
    """Translate a detector match from detection_text → full_text coordinates.

    Works on any NamedTuple with ``start``, ``end``, ``text`` fields
    (``RegexMatch``, ``NERMatch``, ``GLiNERMatch``, ``LLMMatch``).

    Algorithm:
    - Walk ``dt_to_ft[start:end]`` forward to find the first mapped pt → ft_start
    - Walk backward to find the last mapped pt → ft_end_char
    - ``region.char_end = ft_end_char + 1``
    - ``region.text = full_text[ft_start:ft_end].replace('\\n', ' ')``

    Returns the translated match, or *None* if the matched span maps
    entirely to inserted separator characters (very unlikely in practice).
    """
    ds, de = match.start, match.end
    n = len(dt_to_ft)

    # First real full_text position at or after ds
    ft_start = -1
    for i in range(max(0, ds), min(de, n)):
        v = dt_to_ft[i]
        if v >= 0:
            ft_start = v
            break

    if ft_start < 0:
        return None

    # Last real full_text position strictly before de
    ft_end_char = -1
    for i in range(min(de, n) - 1, max(0, ds) - 1, -1):
        v = dt_to_ft[i]
        if v >= 0:
            ft_end_char = v
            break

    if ft_end_char < 0:
        return None

    ft_end = ft_end_char + 1
    # Normalise: replace any embedded newlines with spaces so the stored
    # region.text is clean (newlines can appear when a match straddles a
    # line boundary that sits between two real word characters).
    ft_text = full_text[ft_start:ft_end].replace("\n", " ")
    return match._replace(start=ft_start, end=ft_end, text=ft_text)
