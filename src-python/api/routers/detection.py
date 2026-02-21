"""PII detection, re-detection, and detection progress."""

from __future__ import annotations

import logging
import os
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as _PydanticBaseModel, Field

from core.config import config
from core.detection.noise_filters import has_legal_suffix as _has_legal_suffix
from models.schemas import (
    BBox,
    DetectionProgressResponse,
    DocumentStatus,
    PIIRegion,
    ResetDetectionResponse,
)
from api.deps import (
    cleanup_stale_progress,
    detection_progress,
    get_active_llm_engine,
    get_doc,
    save_doc,
    acquire_detection_lock,
    release_detection_lock,
    acquire_config_lock,
    release_config_lock,
    config_override,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["detection"])

# P1: max parallel workers for page detection.
# ThreadPoolExecutor releases GIL during spaCy/PyTorch C-extension work,
# giving real parallelism for multi-page documents.
_MAX_DETECTION_WORKERS = min(4, os.cpu_count() or 2)


@router.get("/documents/{doc_id}/detection-progress")
async def get_detection_progress(doc_id: str) -> dict[str, Any]:
    """Return real-time detection progress for a document."""
    # Evict stale entries on each poll
    cleanup_stale_progress()
    progress = detection_progress.get(doc_id)
    if progress is None:
        return {
            "doc_id": doc_id,
            "status": "idle",
            "current_page": 0,
            "total_pages": 0,
            "pages_done": 0,
            "regions_found": 0,
            "elapsed_seconds": 0.0,
            "page_statuses": [],
        }
    # Update elapsed time
    progress["elapsed_seconds"] = _time.time() - progress.get("_started_at", _time.time())
    # Return a clean copy (exclude internal keys)
    return {k: v for k, v in progress.items() if not k.startswith("_")}


@router.post("/documents/{doc_id}/detect")
async def detect_pii(doc_id: str) -> dict[str, Any]:
    """Run PII detection on all pages of a document."""
    import asyncio
    import traceback

    doc = get_doc(doc_id)  # 404 before heavy imports

    if not acquire_detection_lock(doc_id):
        raise HTTPException(409, detail="Detection already in progress. Please wait.")

    try:
        from core.detection.pipeline import detect_pii_on_page, propagate_regions_across_pages
        from core.detection.propagation import propagate_partial_org_names
        from core.detection.language import detect_language
        doc.status = DocumentStatus.DETECTING
        doc.regions = []

        engine = get_active_llm_engine()
        total_pages = len(doc.pages)

        # When a specific language is configured, pass it through so
        # per-page detection is skipped.  In auto mode leave it None so
        # each page detects its own language independently (supports
        # mixed-language documents).
        doc_language: str | None = None
        if config.detection_language and config.detection_language != "auto":
            doc_language = config.detection_language

        # Initialize progress tracker
        # Build the list of pipeline steps that will run for progress display
        _pipeline_steps: list[str] = []
        if config.regex_enabled:
            _pipeline_steps.append("regex")
        if config.ner_enabled:
            _pipeline_steps.append("ner")
            from core.detection.gliner_detector import is_gliner_available as _is_gli
            if _is_gli():
                _pipeline_steps.append("gliner")
        if config.llm_detection_enabled and engine is not None:
            _pipeline_steps.append("llm")
        _pipeline_steps.append("merge")

        detection_progress[doc_id] = {
            "doc_id": doc_id,
            "status": "running",
            "current_page": 0,
            "total_pages": total_pages,
            "pages_done": 0,
            "regions_found": 0,
            "elapsed_seconds": 0.0,
            "pipeline_steps": _pipeline_steps,
            "page_statuses": [
                {"page": i + 1, "status": "pending", "regions": 0, "pipeline_step": ""}
                for i in range(total_pages)
            ],
            "_started_at": _time.time(),
        }

        def _run_detection() -> list[PIIRegion]:
            """Run detection on all pages using parallel threads."""
            progress = detection_progress[doc_id]
            n_pages = len(doc.pages)
            workers = min(_MAX_DETECTION_WORKERS, n_pages)
            page_results: dict[int, list[PIIRegion]] = {}

            def _detect_one(idx: int, page):
                progress["page_statuses"][idx]["status"] = "running"
                def _step_cb(step: str) -> None:
                    progress["page_statuses"][idx]["pipeline_step"] = step
                regions = detect_pii_on_page(
                    page, llm_engine=engine,
                    predetected_language=doc_language,
                    progress_callback=_step_cb,
                )
                progress["page_statuses"][idx]["status"] = "done"
                progress["page_statuses"][idx]["regions"] = len(regions)
                return idx, regions

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_detect_one, idx, page): idx
                    for idx, page in enumerate(doc.pages)
                }
                for future in as_completed(futures):
                    idx, regions = future.result()
                    page_results[idx] = regions
                    progress["pages_done"] = len(page_results)
                    progress["regions_found"] = sum(len(r) for r in page_results.values())
                    progress["current_page"] = idx + 1
                    progress["elapsed_seconds"] = _time.time() - progress["_started_at"]

            # Reassemble in page order
            all_regions: list[PIIRegion] = []
            for idx in sorted(page_results):
                all_regions.extend(page_results[idx])
            return all_regions

        # Run CPU-bound detection in a thread pool
        all_regions = await asyncio.to_thread(_run_detection)

        # Propagate: if text was detected on one page, flag it on every
        # other page where it also appears.
        doc.regions = propagate_regions_across_pages(all_regions, doc.pages)

        # Partial ORG propagation: flag 2+-word sub-phrases of known ORG names
        doc.regions = propagate_partial_org_names(doc.regions, doc.pages)

        # Type unification: ensure same text → single type across the document
        from core.detection.propagation import unify_types_by_text
        doc.regions = unify_types_by_text(doc.regions)

        # Final sweep: drop any ORG region with digit-only or very short text
        # Exception: numbered companies with legal suffixes (e.g., "9169270 Canada Inc.")
        from models.schemas import PIIType as _PIIType
        _org_before = len(doc.regions)
        doc.regions = [
            r for r in doc.regions
            if not (
                r.pii_type == _PIIType.ORG
                and (
                    len(r.text.strip()) <= 2
                    or r.text.strip().isdigit()
                    or (
                        r.text.strip()
                        and r.text.strip()[0].isdigit()
                        and not _has_legal_suffix(r.text)
                    )
                )
            )
        ]
        _org_swept = _org_before - len(doc.regions)
        if _org_swept:
            logger.info(f"Final ORG sweep removed {_org_swept} digit/short ORG(s)")

        doc.status = DocumentStatus.REVIEWING
        logger.info(f"Detection complete for '{doc.original_filename}': {len(doc.regions)} regions")

        save_doc(doc)

        # Mark progress as complete
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "complete"
            detection_progress[doc_id]["elapsed_seconds"] = (
                _time.time() - detection_progress[doc_id].get("_started_at", _time.time())
            )

        return {
            "doc_id": doc_id,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Detection failed: {e}\n{tb}")
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "error"
            detection_progress[doc_id]["error"] = str(e)
        raise HTTPException(500, detail="Detection failed. Check server logs for details.")
    finally:
        release_detection_lock(doc_id)


class RedetectRequest(_PydanticBaseModel):
    """Request body for the redetect (autodetect) endpoint."""
    # M10: Add ge/le bounds to confidence_threshold
    confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    page_number: Optional[int] = None  # None = all pages
    regex_enabled: bool = True
    ner_enabled: bool = True
    llm_detection_enabled: bool = True
    regex_types: Optional[list[str]] = None   # None = all types; e.g. ["EMAIL", "SSN"]
    ner_types: Optional[list[str]] = None     # None = all types; e.g. ["PERSON", "ORG"]
    blacklist_terms: Optional[list[str]] = None  # terms to search for (highest priority)
    blacklist_action: str = "none"               # "none" | "tokenize" | "remove"
    blacklist_fuzziness: float = Field(default=1.0, ge=0.5, le=1.0)  # 1.0 = exact, lower = fuzzy


@router.post("/documents/{doc_id}/redetect")
async def redetect_pii(doc_id: str, body: RedetectRequest) -> dict[str, Any]:
    """Re-run PII detection with custom fuzziness (confidence threshold).

    On success, all existing regions on the scanned pages are replaced with
    the fresh detections.  Regions on non-scanned pages (when scope is a
    single page) are kept.
    """
    import asyncio
    import traceback

    doc = get_doc(doc_id)  # 404 before heavy imports

    if not acquire_detection_lock(doc_id):
        raise HTTPException(409, detail="Detection already in progress. Please wait.")
    if not acquire_config_lock(doc_id):
        release_detection_lock(doc_id)
        raise HTTPException(409, detail="Another detection with custom settings is running. Please wait.")

    try:
        from core.detection.pipeline import detect_pii_on_page, propagate_regions_across_pages
        from core.detection.propagation import propagate_partial_org_names as _prop_partial_orgs_r
        from core.detection.language import detect_language as _detect_lang_r

        # Thread-safe config override for this detection run
        with config_override(
            confidence_threshold=body.confidence_threshold,
            regex_enabled=body.regex_enabled,
            ner_enabled=body.ner_enabled,
            llm_detection_enabled=body.llm_detection_enabled,
            regex_types=body.regex_types,
            ner_types=body.ner_types,
        ):
            engine = get_active_llm_engine()

            # Determine which pages to scan
            pages_to_scan = doc.pages
            if body.page_number is not None:
                pages_to_scan = [p for p in doc.pages if p.page_number == body.page_number]
                if not pages_to_scan:
                    raise HTTPException(404, detail=f"Page {body.page_number} not found")

            total_pages = len(pages_to_scan)

            # When a specific language is configured, pass it through.
            # In auto mode leave None so each page detects independently
            # (correct for mixed-language documents).
            _redetect_lang: str | None = None
            if config.detection_language and config.detection_language != "auto":
                _redetect_lang = config.detection_language

            # Build the list of pipeline steps for progress display
            _redet_pipeline_steps: list[str] = []
            if config.regex_enabled:
                _redet_pipeline_steps.append("regex")
            if config.ner_enabled:
                _redet_pipeline_steps.append("ner")
                from core.detection.gliner_detector import is_gliner_available as _is_gli_r
                if _is_gli_r():
                    _redet_pipeline_steps.append("gliner")
            if config.llm_detection_enabled and engine is not None:
                _redet_pipeline_steps.append("llm")
            _redet_pipeline_steps.append("merge")

            # Initialize progress tracker (same format as initial detect)
            detection_progress[doc_id] = {
                "doc_id": doc_id,
                "status": "running",
                "current_page": 0,
                "total_pages": total_pages,
                "pages_done": 0,
                "regions_found": 0,
                "elapsed_seconds": 0.0,
                "pipeline_steps": _redet_pipeline_steps,
                "page_statuses": [
                    {"page": p.page_number, "status": "pending", "regions": 0, "pipeline_step": ""}
                    for p in pages_to_scan
                ],
                "_started_at": _time.time(),
            }

            def _run_redetection() -> list[PIIRegion]:
                """Run re-detection on selected pages in parallel threads."""
                progress = detection_progress[doc_id]
                n = len(pages_to_scan)
                workers = min(_MAX_DETECTION_WORKERS, n)
                page_results: dict[int, list[PIIRegion]] = {}

                def _detect_one(idx: int, page):
                    progress["page_statuses"][idx]["status"] = "running"
                    def _step_cb(step: str) -> None:
                        progress["page_statuses"][idx]["pipeline_step"] = step
                    detected = detect_pii_on_page(
                        page, llm_engine=engine,
                        predetected_language=_redetect_lang,
                        progress_callback=_step_cb,
                    )
                    progress["page_statuses"][idx]["status"] = "done"
                    progress["page_statuses"][idx]["regions"] = len(detected)
                    return idx, detected

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {
                        pool.submit(_detect_one, idx, page): idx
                        for idx, page in enumerate(pages_to_scan)
                    }
                    for future in as_completed(futures):
                        idx, detected = future.result()
                        page_results[idx] = detected
                        progress["pages_done"] = len(page_results)
                        progress["regions_found"] = sum(len(r) for r in page_results.values())
                        progress["current_page"] = pages_to_scan[idx].page_number
                        progress["elapsed_seconds"] = _time.time() - progress["_started_at"]

                results: list[PIIRegion] = []
                for idx in sorted(page_results):
                    results.extend(page_results[idx])
                return results

            new_regions = await asyncio.to_thread(_run_redetection)

        # ── Normalise apostrophe / quote variants to ASCII ──
        # So that user input with smart-quotes matches OCR text.
        import unicodedata as _ud
        _QUOTE_MAP = str.maketrans({
            0x2018: "'",  # LEFT SINGLE QUOTATION MARK
            0x2019: "'",  # RIGHT SINGLE QUOTATION MARK
            0x201A: "'",  # SINGLE LOW-9 QUOTATION MARK
            0x02BC: "'",  # MODIFIER LETTER APOSTROPHE
            0x02BB: "'",  # MODIFIER LETTER TURNED COMMA
            0xFF07: "'",  # FULLWIDTH APOSTROPHE
            0x201C: '"',  # LEFT DOUBLE QUOTATION MARK
            0x201D: '"',  # RIGHT DOUBLE QUOTATION MARK
            0x201E: '"',  # DOUBLE LOW-9 QUOTATION MARK
            0xFF02: '"',  # FULLWIDTH QUOTATION MARK
        })

        def _norm_quotes(s: str) -> str:
            return s.translate(_QUOTE_MAP)

        # ── Blacklist: text-search for user-specified terms (highest priority) ──
        blacklist_created = 0
        if body.blacklist_terms:
            from core.detection.pipeline import _compute_block_offsets
            import uuid as _uuid
            from models.schemas import PIIType as _PIIType, DetectionSource as _DetSource, RegionAction as _RAct

            bl_action_map = {"tokenize": _RAct.TOKENIZE, "remove": _RAct.REMOVE}
            bl_target_action: _RAct | None = bl_action_map.get(body.blacklist_action)

            # Deduplicate terms (case-insensitive)
            _bl_seen: set[str] = set()
            bl_terms: list[str] = []
            for t in body.blacklist_terms:
                tc = t.strip()
                tl = tc.lower()
                if tc and tl not in _bl_seen:
                    _bl_seen.add(tl)
                    bl_terms.append(tc)

            bl_regions: list[PIIRegion] = []

            for page in pages_to_scan:
                ft = page.full_text
                if not ft:
                    continue
                block_offsets = _compute_block_offsets(page.text_blocks, ft)

                # Build accent-stripped, quote-normalised lowercase text with index mapping
                _nfd = _ud.normalize("NFD", _norm_quotes(ft.lower()))
                _norm_chars: list[str] = []
                _n2o: list[int] = []
                _seen_nfd = 0
                for _ci in range(len(ft)):
                    _clen = len(_ud.normalize("NFD", ft[_ci]))
                    for _ in range(_clen):
                        if _seen_nfd < len(_nfd) and _ud.category(_nfd[_seen_nfd]) != "Mn":
                            _norm_chars.append(_nfd[_seen_nfd])
                            _n2o.append(_ci)
                        _seen_nfd += 1
                _n2o.append(len(ft))  # sentinel
                ft_norm = "".join(_norm_chars)

                for needle in bl_terms:
                    nl = "".join(
                        c for c in _ud.normalize("NFD", _norm_quotes(needle.lower()))
                        if _ud.category(c) != "Mn"
                    )
                    nlen = len(nl)
                    if nlen == 0:
                        continue

                    # Determine fuzzy vs exact matching
                    _bl_fuzz = body.blacklist_fuzziness
                    _use_fuzzy = _bl_fuzz < 0.98

                    if _use_fuzzy:
                        # Fuzzy matching via the 'regex' module's {e<=N} syntax
                        import regex as _rx
                        max_errors = max(1, round(nlen * (1.0 - _bl_fuzz)))
                        # Escape the needle for regex, then wrap with fuzzy spec
                        _escaped = _rx.escape(nl)
                        _fpat = _rx.compile(
                            rf"(?b)({_escaped}){{e<={max_errors}}}",
                            _rx.IGNORECASE,
                        )
                        for _fm in _fpat.finditer(ft_norm, overlapped=False):
                            ni = _fm.start()
                            ni_end = _fm.end()
                            idx = _n2o[ni]
                            m_end = _n2o[min(ni_end, len(_n2o) - 1)]

                            # Map char range → bbox
                            hits = [blk for cs, ce, blk in block_offsets if ce > idx and cs < m_end]
                            if not hits:
                                continue
                            bx0 = max(0.0, min(b.bbox.x0 for b in hits))
                            by0 = max(0.0, min(b.bbox.y0 for b in hits))
                            bx1 = min(page.width, max(b.bbox.x1 for b in hits))
                            by1 = min(page.height, max(b.bbox.y1 for b in hits))

                            r = PIIRegion(
                                page_number=page.page_number,
                                bbox=BBox(x0=round(bx0, 2), y0=round(by0, 2),
                                          x1=round(bx1, 2), y1=round(by1, 2)),
                                text=ft[idx:m_end],
                                pii_type=_PIIType.CUSTOM,
                                confidence=1.0,
                                source=_DetSource.MANUAL,
                                action=bl_target_action if bl_target_action else _RAct.PENDING,
                                char_start=idx,
                                char_end=m_end,
                            )
                            r.id = _uuid.uuid4().hex[:12]
                            bl_regions.append(r)
                    else:
                        # Exact matching (current behaviour)
                        pos = 0
                        while True:
                            ni = ft_norm.find(nl, pos)
                            if ni == -1:
                                break
                            pos = ni + 1
                            idx = _n2o[ni]
                            m_end = _n2o[min(ni + nlen, len(_n2o) - 1)]

                            # Map char range → bbox
                            hits = [blk for cs, ce, blk in block_offsets if ce > idx and cs < m_end]
                            if not hits:
                                continue
                            bx0 = max(0.0, min(b.bbox.x0 for b in hits))
                            by0 = max(0.0, min(b.bbox.y0 for b in hits))
                            bx1 = min(page.width, max(b.bbox.x1 for b in hits))
                            by1 = min(page.height, max(b.bbox.y1 for b in hits))

                            r = PIIRegion(
                                page_number=page.page_number,
                                bbox=BBox(x0=round(bx0, 2), y0=round(by0, 2),
                                          x1=round(bx1, 2), y1=round(by1, 2)),
                                text=ft[idx:m_end],
                                pii_type=_PIIType.CUSTOM,
                                confidence=1.0,
                                source=_DetSource.MANUAL,
                                action=bl_target_action if bl_target_action else _RAct.PENDING,
                                char_start=idx,
                                char_end=m_end,
                            )
                            r.id = _uuid.uuid4().hex[:12]
                            bl_regions.append(r)

            blacklist_created = len(bl_regions)
            # Prepend blacklist regions so they get highest priority in merge
            new_regions = bl_regions + new_regions
            if blacklist_created:
                logger.info("Blacklist: %d regions from %d terms", blacklist_created, len(bl_terms))

        # ── Trim auto-detected regions to match user expressions ──
        # When the user specifies exact expressions (blacklist terms or
        # manual regions), auto-detectors like GLiNER may return a span
        # that starts with the expression but extends beyond it (e.g.
        # "L'ESPRIT DU REPRENEURIAT\n(série documentaire…)").  The user's
        # expression should always win — trim the auto-detected region.
        from models.schemas import DetectionSource as _DetSrcTrim
        from core.detection.pipeline import _compute_block_offsets as _cbo_trim
        from core.text_utils import normalize_for_matching as _nfm

        _trim_exprs: list[str] = []
        if body.blacklist_terms:
            _trim_exprs.extend(t.strip() for t in bl_terms if t.strip())
        # Also include existing MANUAL region texts as user expressions
        for _er in doc.regions:
            if _er.source == _DetSrcTrim.MANUAL and _er.text.strip():
                _trim_exprs.append(_er.text.strip())
        if _trim_exprs:
            _expr_norms = list({_nfm(e): e for e in _trim_exprs}.items())  # dedupe by normalised form
            _trimmed_count = 0
            for nr in new_regions:
                if nr.source == _DetSrcTrim.MANUAL:
                    continue
                nr_norm = _nfm(nr.text)
                for expr_norm, expr_raw in _expr_norms:
                    if not expr_norm or len(nr_norm) <= len(expr_norm):
                        continue
                    if not nr_norm.startswith(expr_norm):
                        continue
                    # Extra text beyond the expression — only trim if
                    # the boundary is a non-alpha char (space, newline, paren).
                    extra_char = nr_norm[len(expr_norm)]
                    if extra_char.isalpha():
                        continue
                    # Find the trim point in the original region text.
                    # Walk the original text to find where the expression ends
                    # by matching normalised character counts.
                    orig_pos = 0
                    norm_consumed = 0
                    while orig_pos < len(nr.text) and norm_consumed < len(expr_norm):
                        ch_norm = _nfm(nr.text[orig_pos])
                        norm_consumed += len(ch_norm)
                        orig_pos += 1
                    if orig_pos > 0 and orig_pos < len(nr.text):
                        old_text = nr.text
                        nr.text = nr.text[:orig_pos].rstrip()
                        nr.char_end = nr.char_start + len(nr.text)
                        # Recompute bbox from the trimmed char range
                        page = next((p for p in pages_to_scan if p.page_number == nr.page_number), None)
                        if page:
                            _bo = _cbo_trim(page.text_blocks, page.full_text)
                            _hits = [blk for cs, ce, blk in _bo if ce > nr.char_start and cs < nr.char_end]
                            if _hits:
                                nr.bbox = BBox(
                                    x0=round(max(0.0, min(b.bbox.x0 for b in _hits)), 2),
                                    y0=round(max(0.0, min(b.bbox.y0 for b in _hits)), 2),
                                    x1=round(min(page.width, max(b.bbox.x1 for b in _hits)), 2),
                                    y1=round(min(page.height, max(b.bbox.y1 for b in _hits)), 2),
                                )
                        _trimmed_count += 1
                        logger.debug(
                            "Trimmed auto-detected region to user expression: %r -> %r",
                            old_text[:60], nr.text[:60],
                        )
                        break  # one trim per region
            if _trimmed_count:
                logger.info("Trimmed %d auto-detected region(s) to match user expressions", _trimmed_count)

        # ── Replace regions on scanned pages with fresh detections ──
        # Old regions on scanned pages are discarded; regions on
        # non-scanned pages (when scope is a single page) are kept.
        scanned_pages = {p.page_number for p in pages_to_scan}
        existing_other = [r for r in doc.regions if r.page_number not in scanned_pages]
        old_count = len(doc.regions) - len(existing_other)
        added_count = len(new_regions)

        # Build set of PII types that were explicitly excluded by the user
        # so we can strip them after propagation.
        _regex_tab_types = {"EMAIL", "PHONE", "SSN", "CREDIT_CARD", "IBAN", "DATE",
                            "IP_ADDRESS", "PASSPORT", "DRIVER_LICENSE", "ADDRESS"}
        _ner_tab_types = {"PERSON", "ORG", "LOCATION", "CUSTOM"}
        excluded_types: set[str] = set()
        if body.regex_enabled and body.regex_types is not None:
            excluded_types |= _regex_tab_types - set(body.regex_types)
        if not body.regex_enabled:
            excluded_types |= _regex_tab_types
        if body.ner_enabled and body.ner_types is not None:
            excluded_types |= _ner_tab_types - set(body.ner_types)
        if not body.ner_enabled:
            excluded_types |= _ner_tab_types

        from models.schemas import DetectionSource
        merged_regions = existing_other + new_regions

        # Propagate newly detected text across all pages
        all_regions = propagate_regions_across_pages(merged_regions, doc.pages)

        # Partial ORG propagation: flag 2+-word sub-phrases and single-word
        # subsets of known ORG names across all pages
        all_regions = _prop_partial_orgs_r(all_regions, doc.pages)

        # Post-propagation: strip excluded types from the scanned pages
        # (propagation may re-create them from templates on other pages)
        # Never strip MANUAL regions (blacklist / user-drawn).
        if excluded_types:
            all_regions = [
                r for r in all_regions
                if r.source == DetectionSource.MANUAL
                or r.page_number not in scanned_pages
                or (r.pii_type.value if hasattr(r.pii_type, 'value') else str(r.pii_type)) not in excluded_types
            ]

        doc.regions = all_regions

        # Type unification: ensure same text → single type across the document
        from core.detection.propagation import unify_types_by_text as _unify_r
        doc.regions = _unify_r(doc.regions)

        # Final sweep: drop any ORG region with digit-only or very short text
        # Exception: numbered companies with legal suffixes (e.g., "9169270 Canada Inc.")
        from models.schemas import PIIType as _PIIType
        _org_before_r = len(doc.regions)
        doc.regions = [
            r for r in doc.regions
            if not (
                r.pii_type == _PIIType.ORG
                and (
                    len(r.text.strip()) <= 2
                    or r.text.strip().isdigit()
                    or (
                        r.text.strip()
                        and r.text.strip()[0].isdigit()
                        and not _has_legal_suffix(r.text)
                    )
                )
            )
        ]
        _org_swept_r = _org_before_r - len(doc.regions)
        if _org_swept_r:
            logger.info(f"Redetect: final ORG sweep removed {_org_swept_r} digit/short ORG(s)")

        doc.status = DocumentStatus.REVIEWING
        save_doc(doc)

        # Mark progress as complete
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "complete"
            detection_progress[doc_id]["regions_found"] = len(doc.regions)
            detection_progress[doc_id]["elapsed_seconds"] = (
                _time.time() - detection_progress[doc_id].get("_started_at", _time.time())
            )

        logger.info(
            f"Redetect for '{doc.original_filename}' "
            f"(threshold={body.confidence_threshold}, pages={body.page_number or 'all'}): "
            f"cleared {old_count} old, {added_count} new, "
            f"{len(doc.regions)} total"
        )

        return {
            "doc_id": doc_id,
            "added": added_count,
            "updated": 0,
            "removed": old_count,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Redetect failed: {e}\n{tb}")
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "error"
            detection_progress[doc_id]["error"] = str(e)
        raise HTTPException(500, detail="Redetect failed. Check server logs for details.")
    finally:
        release_config_lock()
        release_detection_lock(doc_id)


@router.post("/documents/{doc_id}/reset-detection")
async def reset_detection(doc_id: str) -> dict[str, Any]:
    """Clear ALL regions for a document and re-run fresh detection from scratch.

    Unlike ``/redetect`` (which merges), this wipes every region — including
    user-acted ones — and runs the detection pipeline as if the document had
    just been uploaded.  Use this when persisted data from an older detection
    run is corrupt or stale.
    """
    import asyncio
    import traceback

    doc = get_doc(doc_id)

    if not acquire_detection_lock(doc_id):
        raise HTTPException(409, detail="Detection already in progress. Please wait.")

    try:
        from core.detection.pipeline import detect_pii_on_page, propagate_regions_across_pages
        from core.detection.propagation import propagate_partial_org_names
        from core.detection.language import detect_language as _detect_lang

        old_count = len(doc.regions)
        doc.status = DocumentStatus.DETECTING
        doc.regions = []

        engine = get_active_llm_engine()
        total_pages = len(doc.pages)

        # Per-page language detection: only force a single language when
        # the user explicitly chose one (not "auto").
        _reset_lang: str | None = None
        if config.detection_language and config.detection_language != "auto":
            _reset_lang = config.detection_language

        detection_progress[doc_id] = {
            "doc_id": doc_id,
            "status": "running",
            "current_page": 0,
            "total_pages": total_pages,
            "pages_done": 0,
            "regions_found": 0,
            "elapsed_seconds": 0.0,
            "page_statuses": [
                {"page": p.page_number, "status": "pending", "regions": 0}
                for p in doc.pages
            ],
            "_started_at": _time.time(),
        }

        def _run() -> list[PIIRegion]:
            """Run fresh detection on all pages using parallel threads."""
            progress = detection_progress[doc_id]
            n_pages = len(doc.pages)
            workers = min(_MAX_DETECTION_WORKERS, n_pages)
            page_results: dict[int, list[PIIRegion]] = {}

            def _detect_one(idx: int, page):
                progress["page_statuses"][idx]["status"] = "running"
                regions = detect_pii_on_page(
                    page, llm_engine=engine,
                    predetected_language=_reset_lang,
                )
                progress["page_statuses"][idx]["status"] = "done"
                progress["page_statuses"][idx]["regions"] = len(regions)
                return idx, regions

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_detect_one, idx, page): idx
                    for idx, page in enumerate(doc.pages)
                }
                for future in as_completed(futures):
                    idx, regions = future.result()
                    page_results[idx] = regions
                    progress["pages_done"] = len(page_results)
                    progress["regions_found"] = sum(len(r) for r in page_results.values())
                    progress["current_page"] = idx + 1
                    progress["elapsed_seconds"] = _time.time() - progress["_started_at"]

            all_regions: list[PIIRegion] = []
            for idx in sorted(page_results):
                all_regions.extend(page_results[idx])
            return all_regions

        all_regions = await asyncio.to_thread(_run)
        doc.regions = propagate_regions_across_pages(all_regions, doc.pages)
        doc.regions = propagate_partial_org_names(doc.regions, doc.pages)

        # Type unification: ensure same text → single type across the document
        from core.detection.propagation import unify_types_by_text as _unify_reset
        doc.regions = _unify_reset(doc.regions)

        doc.status = DocumentStatus.REVIEWING
        save_doc(doc)

        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "complete"
            detection_progress[doc_id]["regions_found"] = len(doc.regions)
            detection_progress[doc_id]["elapsed_seconds"] = (
                _time.time() - detection_progress[doc_id].get("_started_at", _time.time())
            )

        logger.info(
            "Reset detection for '%s': cleared %d old regions, found %d fresh",
            doc.original_filename, old_count, len(doc.regions),
        )

        return {
            "doc_id": doc_id,
            "cleared": old_count,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Reset detection failed: {e}\n{tb}")
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "error"
            detection_progress[doc_id]["error"] = str(e)
        raise HTTPException(500, detail="Reset detection failed. Check server logs for details.")
    finally:
        release_detection_lock(doc_id)


@router.get("/documents/{doc_id}/regions")
async def get_regions(doc_id: str, page_number: Optional[int] = None) -> list[dict[str, Any]]:
    """Get detected PII regions, optionally filtered by page."""
    doc = get_doc(doc_id)
    regions = doc.regions
    if page_number is not None:
        regions = [r for r in regions if r.page_number == page_number]
    return [r.model_dump(mode="json") for r in regions]
