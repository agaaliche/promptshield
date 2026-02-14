"""Detection merge — combines results from all detector layers into
unified PIIRegion instances with cross-layer boosting, overlap
resolution, noise filtering, and shape enforcement.
"""

from __future__ import annotations

import logging
import re
import uuid

from core.config import config
from core.detection.bbox_utils import _resolve_bbox_overlaps
from core.detection.block_offsets import (
    _clamp_bbox,
    _compute_block_offsets,
    _char_offset_to_bbox,
    _char_offsets_to_line_bboxes,
)
from core.detection.noise_filters import (
    _is_org_pipeline_noise,
    _is_loc_pipeline_noise,
    _is_person_pipeline_noise,
    _is_address_number_only,
    _STRUCTURED_MIN_DIGITS,
)
from core.detection.region_shapes import (
    _enforce_region_shapes,
    _max_lines_for_type,
)
from core.detection.regex_detector import RegexMatch
from core.detection.ner_detector import NERMatch
from core.detection.gliner_detector import GLiNERMatch
from core.detection.llm_detector import LLMMatch
from models.schemas import (
    BBox,
    DetectionSource,
    PIIRegion,
    PIIType,
    PageData,
    TextBlock,
)

logger = logging.getLogger(__name__)


def _merge_detections(
    regex_matches: list[RegexMatch],
    ner_matches: list[NERMatch],
    llm_matches: list[LLMMatch],
    page_data: PageData,
    gliner_matches: list[GLiNERMatch] | None = None,
) -> list[PIIRegion]:
    """Merge detection results from all layers into unified PIIRegion list.

    Strategy:
    1. Convert all matches to a common format with char offsets.
    2. Cross-layer confidence boost when 2+ layers flag the same span.
    3. Sort by start position.
    4. Merge overlapping regions — higher priority source wins.
    5. Apply noise filters and shape constraints.
    """
    structured_types = {
        PIIType.SSN, PIIType.EMAIL, PIIType.PHONE,
        PIIType.CREDIT_CARD, PIIType.IBAN, PIIType.IP_ADDRESS,
        PIIType.DATE,
    }
    semi_structured_types = {PIIType.ORG, PIIType.ADDRESS}

    # ── Convert to common intermediate format ────────────────────────
    candidates: list[dict] = []

    for m in regex_matches:
        if m.pii_type in structured_types:
            prio = 3
        elif m.pii_type in semi_structured_types:
            prio = 2
        else:
            prio = 1
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.REGEX,
            "priority": prio,
        })

    for m in ner_matches:
        if m.pii_type in (PIIType.PHONE, PIIType.SSN, PIIType.DRIVER_LICENSE):
            digits = sum(c.isdigit() for c in m.text)
            if m.pii_type == PIIType.PHONE and digits < 7:
                logger.debug("Skipping NER PHONE with too few digits: %r", m.text)
                continue
            if m.pii_type == PIIType.SSN and digits < 7:
                logger.debug("Skipping NER SSN with too few digits: %r", m.text)
                continue
            if m.pii_type == PIIType.DRIVER_LICENSE and digits < 6:
                logger.debug("Skipping NER DRIVER_LICENSE with too few digits: %r", m.text)
                continue
            if m.pii_type in (PIIType.PHONE, PIIType.SSN) and "." in m.text:
                logger.debug("Skipping NER %s with decimal point (financial): %r", m.pii_type.value, m.text)
                continue
            if m.pii_type in (PIIType.PHONE, PIIType.SSN) and "_" in m.text:
                logger.debug("Skipping NER %s with underscore (OCR artifact): %r", m.pii_type.value, m.text)
                continue
        if m.pii_type == PIIType.PASSPORT:
            if "-" in m.text or "(" in m.text or ")" in m.text:
                logger.debug("Skipping NER PASSPORT with phone formatting: %r", m.text)
                continue
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.NER,
            "priority": 2,
        })

    for m in (gliner_matches or []):
        if m.pii_type in (PIIType.PHONE, PIIType.SSN, PIIType.DRIVER_LICENSE):
            if "." in m.text and any(c.isdigit() for c in m.text):
                digits = sum(c.isdigit() for c in m.text)
                non_digit = len(m.text.strip()) - digits
                if "," in m.text or non_digit > 2:
                    logger.debug("Skipping GLiNER %s (looks like currency): %r", m.pii_type, m.text)
                    continue
            digits = sum(c.isdigit() for c in m.text)
            if m.pii_type == PIIType.PHONE and digits < 7:
                continue
            if m.pii_type == PIIType.SSN and digits < 7:
                continue
            if m.pii_type == PIIType.DRIVER_LICENSE and digits < 6:
                continue
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.GLINER,
            "priority": 2,
        })

    for m in llm_matches:
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.LLM,
            "priority": 1 if m.pii_type in structured_types else 3,
        })

    # ── Cross-layer confidence boost ─────────────────────────────────
    _BOOST_2_LAYERS = 0.10
    _BOOST_3_LAYERS = 0.15

    idx_sorted = sorted(range(len(candidates)), key=lambda k: candidates[k]["start"])

    for ii in range(len(idx_sorted)):
        i = idx_sorted[ii]
        c = candidates[i]
        overlapping_sources: set[str] = {c["source"]}
        c_end = c["end"]

        for jj in range(ii + 1, len(idx_sorted)):
            j = idx_sorted[jj]
            other = candidates[j]
            if other["start"] >= c_end:
                break
            overlap_start = max(c["start"], other["start"])
            overlap_end = min(c_end, other["end"])
            if overlap_end <= overlap_start:
                continue
            overlap_len = overlap_end - overlap_start
            c_len = c_end - c["start"]
            o_len = other["end"] - other["start"]
            if c_len > 0 and o_len > 0:
                ratio = overlap_len / min(c_len, o_len)
                if ratio >= 0.5:
                    overlapping_sources.add(other["source"])

        n_layers = len(overlapping_sources)
        if n_layers >= 3:
            c["confidence"] = min(1.0, c["confidence"] + _BOOST_3_LAYERS)
        elif n_layers == 2:
            c["confidence"] = min(1.0, c["confidence"] + _BOOST_2_LAYERS)

    # ── Sort and merge overlapping regions ────────────────────────────
    candidates.sort(key=lambda x: (x["start"], -x["priority"]))

    merged: list[dict] = []
    for cand in candidates:
        if not merged:
            merged.append(cand)
            continue

        last = merged[-1]
        if cand["start"] < last["end"]:
            if cand["priority"] > last["priority"]:
                merged[-1] = cand
            elif cand["priority"] == last["priority"] and cand["confidence"] > last["confidence"]:
                merged[-1] = cand
            if cand["end"] > last["end"]:
                merged[-1]["end"] = cand["end"]
                merged[-1]["text"] = page_data.full_text[merged[-1]["start"]:cand["end"]]
        else:
            merged.append(cand)

    # ── Apply pipeline-level noise filters ────────────────────────────
    for item in merged:
        if item["pii_type"] == PIIType.ORG:
            logger.debug(
                "Page %d: ORG candidate: text=%r source=%s conf=%.2f noise=%s",
                page_data.page_number, item["text"], item["source"],
                item["confidence"], _is_org_pipeline_noise(item["text"]),
            )

    org_before = len(merged)
    merged = [
        item for item in merged
        if not (item["pii_type"] == PIIType.ORG and _is_org_pipeline_noise(item["text"]))
    ]
    org_dropped = org_before - len(merged)
    if org_dropped:
        logger.info(
            "Page %d: pipeline ORG filter dropped %d noise ORG(s)",
            page_data.page_number, org_dropped,
        )

    loc_before = len(merged)
    merged = [
        item for item in merged
        if not (item["pii_type"] == PIIType.LOCATION and _is_loc_pipeline_noise(item["text"]))
    ]
    loc_dropped = loc_before - len(merged)
    if loc_dropped:
        logger.info(
            "Page %d: pipeline LOCATION filter dropped %d noise LOCATION(s)",
            page_data.page_number, loc_dropped,
        )

    per_before = len(merged)
    merged = [
        item for item in merged
        if not (item["pii_type"] == PIIType.PERSON and _is_person_pipeline_noise(item["text"]))
    ]

    # Context-aware PERSON filter: page-header pattern
    merged = [
        item for item in merged
        if not (
            item["pii_type"] == PIIType.PERSON
            and item.get("source") in ("NER", "GLINER", "BERT")
            and item.get("start", 99) <= 5
            and len(item["text"].split()) >= 2
        )
    ]

    per_dropped = per_before - len(merged)
    if per_dropped:
        logger.info(
            "Page %d: pipeline PERSON filter dropped %d noise PERSON(s)",
            page_data.page_number, per_dropped,
        )

    addr_before = len(merged)
    merged = [
        item for item in merged
        if not (item["pii_type"] == PIIType.ADDRESS and _is_address_number_only(item["text"]))
    ]
    addr_dropped = addr_before - len(merged)
    if addr_dropped:
        logger.info(
            "Page %d: pipeline ADDRESS filter dropped %d invalid ADDRESS(es)",
            page_data.page_number, addr_dropped,
        )

    # ── Post-merge structured digit-count filter ──────────────────────
    struct_before = len(merged)

    def _is_valid_structured(item: dict) -> bool:
        ptype = item["pii_type"]
        min_d = _STRUCTURED_MIN_DIGITS.get(ptype)
        if min_d is None:
            return True
        txt = item["text"]
        digits = sum(c.isdigit() for c in txt)
        if digits < min_d:
            return False
        if ptype == PIIType.SSN and any(c in txt for c in '$€£'):
            return False
        if ptype in (PIIType.SSN, PIIType.PHONE) and '\n' in txt:
            return False
        if ptype == PIIType.SSN:
            if re.fullmatch(r'\d{1,2}\s+\d{3}\s+\d{3}', txt.strip()):
                return False
        return True

    merged = [item for item in merged if _is_valid_structured(item)]
    struct_dropped = struct_before - len(merged)
    if struct_dropped:
        logger.info(
            "Page %d: post-merge structured filter dropped %d region(s)",
            page_data.page_number, struct_dropped,
        )

    # ── Merge adjacent ADDRESS fragments ──────────────────────────────
    _addr_merged: list[dict] = []
    for item in merged:
        if _addr_merged:
            prev = _addr_merged[-1]
            prev_is_addr = prev["pii_type"] == PIIType.ADDRESS
            prev_is_loc = prev["pii_type"] == PIIType.LOCATION
            cur_is_addr = item["pii_type"] == PIIType.ADDRESS
            cur_is_loc = item["pii_type"] == PIIType.LOCATION

            can_merge = False
            if prev_is_addr and (cur_is_addr or cur_is_loc):
                can_merge = True
            elif prev_is_loc and cur_is_addr:
                can_merge = True

            if can_merge:
                gap = item["start"] - prev["end"]
                if 0 <= gap <= 60:
                    combined_text = page_data.full_text[prev["start"]:item["end"]]
                    newline_count = combined_text.count("\n")
                    if newline_count <= 3:
                        prev["end"] = item["end"]
                        prev["text"] = combined_text
                        prev["pii_type"] = PIIType.ADDRESS
                        prev["confidence"] = max(prev["confidence"], item["confidence"])
                        continue
        _addr_merged.append(item)
    if len(_addr_merged) < len(merged):
        logger.debug(
            "Page %d: merged %d adjacent ADDRESS fragment(s)",
            page_data.page_number, len(merged) - len(_addr_merged),
        )
    merged = _addr_merged

    # ── Convert to PIIRegion with per-line bboxes ─────────────────────
    block_offsets = _compute_block_offsets(
        page_data.text_blocks, page_data.full_text,
    )

    _max_pt = config.max_font_size_pt

    regions: list[PIIRegion] = []
    _large_font_skipped = 0
    for item in merged:
        if item["confidence"] < config.confidence_threshold:
            continue
        if item["pii_type"] == PIIType.CUSTOM:
            continue

        line_bboxes = _char_offsets_to_line_bboxes(
            item["start"], item["end"], block_offsets,
        )
        if not line_bboxes:
            bbox = _char_offset_to_bbox(item["start"], item["end"], block_offsets)
            if bbox is None:
                continue
            line_bboxes = [bbox]

        if _max_pt > 0:
            line_bboxes = [b for b in line_bboxes if (b.y1 - b.y0) < _max_pt]
            if not line_bboxes:
                _large_font_skipped += 1
                continue

        # ADDRESS street-number heuristic
        if (
            len(line_bboxes) > 1
            and item["pii_type"] in (PIIType.ADDRESS, "ADDRESS")
        ):
            match_text = page_data.full_text[item["start"]:item["end"]]
            first_line = match_text.split("\n")[0].strip()
            if first_line and not re.search(r"[A-Za-zÀ-ÿ]", first_line):
                continue

        max_lines = _max_lines_for_type(item["pii_type"])

        if len(line_bboxes) == 1:
            regions.append(PIIRegion(
                id=uuid.uuid4().hex[:12],
                page_number=page_data.page_number,
                bbox=line_bboxes[0],
                text=item["text"],
                pii_type=item["pii_type"],
                confidence=item["confidence"],
                source=item["source"],
                char_start=item["start"],
                char_end=item["end"],
            ))
        elif len(line_bboxes) <= max_lines:
            group_id = uuid.uuid4().hex[:12]
            match_text = page_data.full_text[item["start"]:item["end"]]
            line_parts = match_text.split("\n")
            if len(line_parts) == len(line_bboxes):
                line_char_ranges: list[tuple[int, int]] = []
                pos = item["start"]
                for part in line_parts:
                    line_char_ranges.append((pos, pos + len(part)))
                    pos += len(part) + 1
            else:
                line_char_ranges = [(item["start"], item["end"])] * len(line_bboxes)

            for idx, lb in enumerate(line_bboxes):
                cs, ce = line_char_ranges[idx]
                regions.append(PIIRegion(
                    id=uuid.uuid4().hex[:12],
                    page_number=page_data.page_number,
                    bbox=lb,
                    text=item["text"],
                    pii_type=item["pii_type"],
                    confidence=item["confidence"],
                    source=item["source"],
                    char_start=cs,
                    char_end=ce,
                    linked_group=group_id,
                ))
        else:
            match_text = page_data.full_text[item["start"]:item["end"]]
            line_parts = match_text.split("\n")
            if len(line_parts) == len(line_bboxes):
                all_char_ranges: list[tuple[int, int]] = []
                pos = item["start"]
                for part in line_parts:
                    all_char_ranges.append((pos, pos + len(part)))
                    pos += len(part) + 1
            else:
                all_char_ranges = [(item["start"], item["end"])] * len(line_bboxes)

            for i in range(0, len(line_bboxes), max_lines):
                chunk_bboxes = line_bboxes[i:i + max_lines]
                chunk_ranges = all_char_ranges[i:i + max_lines]
                group_id = uuid.uuid4().hex[:12] if len(chunk_bboxes) > 1 else None
                for idx, lb in enumerate(chunk_bboxes):
                    cs, ce = chunk_ranges[idx]
                    regions.append(PIIRegion(
                        id=uuid.uuid4().hex[:12],
                        page_number=page_data.page_number,
                        bbox=lb,
                        text=item["text"],
                        pii_type=item["pii_type"],
                        confidence=item["confidence"],
                        source=item["source"],
                        char_start=cs,
                        char_end=ce,
                        linked_group=group_id,
                    ))

    if _large_font_skipped:
        logger.info(
            "Page %d: filtered %d large-font candidate(s) (bbox height>=%dpt)",
            page_data.page_number, _large_font_skipped, _max_pt,
        )

    # ── Suppress standalone ORGs inside linked groups ─────────────────
    linked_intervals: list[tuple[int, int]] = []
    for r in regions:
        if r.linked_group is not None:
            linked_intervals.append((r.char_start, r.char_end))
    if linked_intervals:
        kept: list[PIIRegion] = []
        for r in regions:
            if (
                r.linked_group is None
                and r.pii_type == PIIType.ORG
                and any(
                    r.char_start >= gs and r.char_end <= ge
                    for gs, ge in linked_intervals
                )
            ):
                continue
            kept.append(r)
        if len(kept) < len(regions):
            logger.debug(
                "Page %d: suppressed %d standalone ORG(s) inside linked groups",
                page_data.page_number, len(regions) - len(kept),
            )
        regions = kept

    # Enforce region shape constraints
    regions = _enforce_region_shapes(regions, page_data, block_offsets)

    # Resolve remaining bbox overlaps
    regions = _resolve_bbox_overlaps(regions)

    # ── FINAL safety net ──────────────────────────────────────────────
    _before_final = len(regions)

    def _is_region_noise(r: PIIRegion) -> bool:
        if r.pii_type == PIIType.ORG and (
            len(r.text.strip()) <= 2
            or r.text.strip().isdigit()
            or _is_org_pipeline_noise(r.text)
        ):
            return True
        if r.pii_type == PIIType.LOCATION and _is_loc_pipeline_noise(r.text):
            return True
        if r.pii_type == PIIType.PERSON and _is_person_pipeline_noise(r.text):
            return True
        if r.pii_type == PIIType.ADDRESS and _is_address_number_only(r.text):
            return True
        _min = _STRUCTURED_MIN_DIGITS.get(r.pii_type)
        if _min is not None:
            digits = sum(c.isdigit() for c in r.text)
            if digits < _min:
                return True
            if r.pii_type == PIIType.SSN and any(c in r.text for c in '$€£'):
                return True
            if r.pii_type in (PIIType.SSN, PIIType.PHONE) and '\n' in r.text:
                return True
        return False

    regions = [r for r in regions if not _is_region_noise(r)]
    _final_dropped = _before_final - len(regions)
    if _final_dropped:
        logger.info(
            "Page %d: FINAL safety net dropped %d noise region(s)",
            page_data.page_number, _final_dropped,
        )

    return regions
