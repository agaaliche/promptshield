"""LLM-based PII detector — Layer 3 of the hybrid pipeline.

Uses the embedded local LLM for contextual PII analysis.
This is the slowest but most capable layer, catching PII that
regex and NER miss (indirect identifiers, contextual info, etc.).

Improvements over a naïve single-pass approach:
- Sliding-window chunking with overlap so long pages aren't truncated.
- Fuzzy / substring matching so minor LLM paraphrases still resolve.
"""

from __future__ import annotations

import json
import logging
import re as _re
from difflib import SequenceMatcher
from typing import NamedTuple

from models.schemas import PIIType

logger = logging.getLogger(__name__)


class LLMMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Extract all personally identifiable information (PII) from the given text. \
The text may be in any language.

Entity types: PERSON (full names), ORG (companies, institutions), EMAIL, \
PHONE, SSN (social security / national ID numbers), CREDIT_CARD, \
ADDRESS (street addresses), LOCATION (places tied to a person), \
DATE (personal dates only, NOT fiscal periods), IP_ADDRESS, PASSPORT, \
DRIVER_LICENSE, CUSTOM (badge/employee IDs, case references).

Rules:
- "text" MUST be the EXACT substring from the source. Do not paraphrase.
- SKIP headers, boilerplate, currency amounts, percentages, page numbers.
- When in doubt, include it.

Return ONLY a JSON array:
[{"text": "exact text", "type": "PERSON", "reason": "brief reason"}]
No PII found: []
"""

USER_PROMPT_TEMPLATE = """\
Find all PII in this text:

{text}

JSON:"""

# ---------------------------------------------------------------------------
# Chunking constants
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 1000             # Characters per chunk sent to LLM
_CHUNK_OVERLAP = 100           # Overlap between consecutive chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Minimum text length to bother sending to the LLM.  Very short
# texts (cover pages, headers) produce degenerate token sequences
# that can trigger NaN/zero-scale assertion failures in ggml.
_MIN_TEXT_LENGTH = 50


def detect_llm(text: str, llm_engine) -> list[LLMMatch]:
    """
    Run LLM-based PII detection with sliding-window chunking.

    Long texts are split into overlapping chunks so no context is lost
    at chunk boundaries.
    """
    stripped = text.strip()
    if not stripped:
        return []

    if len(stripped) < _MIN_TEXT_LENGTH:
        logger.info(
            "LLM skipped — text too short (%d chars < %d minimum)",
            len(stripped), _MIN_TEXT_LENGTH,
        )
        return []

    if llm_engine is None or not llm_engine.is_loaded():
        logger.warning("LLM engine not available — skipping LLM detection")
        return []

    all_matches: list[LLMMatch] = []

    # Short text — single pass
    if len(text) <= _CHUNK_SIZE:
        return _detect_chunk(text, 0, llm_engine)

    # Sliding-window for long text
    offset = 0
    chunk_idx = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]

        chunk_matches = _detect_chunk(chunk, offset, llm_engine)
        all_matches.extend(chunk_matches)
        chunk_idx += 1
        logger.debug(
            f"LLM chunk {chunk_idx}: offset={offset} len={len(chunk)} "
            f"found={len(chunk_matches)}"
        )

        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break

    # Deduplicate matches from overlapping regions
    return _deduplicate(all_matches)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_chunk(
    chunk_text: str,
    global_offset: int,
    llm_engine,
) -> list[LLMMatch]:
    """Run detection on a single chunk and return matches with global offsets."""
    user_prompt = USER_PROMPT_TEMPLATE.format(text=chunk_text)

    try:
        response = llm_engine.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=256,
            temperature=0.1,
            stop=["\n\n\n", "```", "---"],
        )
        logger.info(
            "LLM raw response (chunk offset=%d, %d chars): %s",
            global_offset, len(response), response[:500],
        )
        matches = _parse_llm_response(response, chunk_text, global_offset)
        logger.info("LLM parsed %d matches from chunk at offset %d", len(matches), global_offset)
        return matches
    except Exception as e:
        logger.error(f"LLM detection failed on chunk at offset {global_offset}: {e}")
        return []


def _fuzzy_find(needle: str, haystack: str, threshold: float = 0.75) -> int | None:
    """Find *needle* in *haystack* using fuzzy substring matching.

    Returns the start index in *haystack* or ``None`` if no match above
    *threshold* (0–1 ratio) is found.

    Strategy:
    1. Exact find (fast path).
    2. Case-insensitive find.
    3. Sliding-window SequenceMatcher for fuzzy match.
    """
    # 1. Exact
    idx = haystack.find(needle)
    if idx != -1:
        return idx

    # 2. Case-insensitive
    lower_hay = haystack.lower()
    lower_needle = needle.lower()
    idx = lower_hay.find(lower_needle)
    if idx != -1:
        return idx

    # 3. Fuzzy sliding window
    n = len(needle)
    if n < 3 or n > len(haystack):
        return None

    best_ratio = 0.0
    best_idx = -1
    # Step size — check every character for short needles, skip for long
    step = max(1, n // 6)

    for i in range(0, len(haystack) - n + 1, step):
        window = haystack[i : i + n]
        ratio = SequenceMatcher(None, lower_needle, window.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i

    # Refine around best position (search ±step with step=1)
    if best_idx >= 0 and best_ratio >= threshold * 0.9:
        lo = max(0, best_idx - step)
        hi = min(len(haystack) - n + 1, best_idx + step + 1)
        for i in range(lo, hi):
            window = haystack[i : i + n]
            ratio = SequenceMatcher(None, lower_needle, window.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i

    if best_ratio >= threshold:
        return best_idx

    return None


def _parse_llm_response(
    response: str,
    source_text: str,
    global_offset: int,
) -> list[LLMMatch]:
    """Parse the LLM's JSON response into LLMMatch objects.

    Uses fuzzy matching so minor paraphrases or whitespace differences
    still resolve to the correct location in the source text.
    """
    response = response.strip()

    # Handle markdown code blocks
    if response.startswith("```"):
        lines = response.split("\n")
        response = "\n".join(
            line for line in lines if not line.startswith("```")
        )

    try:
        findings = json.loads(response)
    except json.JSONDecodeError:
        match = _re.search(r"\[.*\]", response, _re.DOTALL)
        if match:
            try:
                findings = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(f"Could not parse LLM JSON: {response[:200]}")
                return []
        else:
            logger.warning(f"No JSON array in LLM response: {response[:200]}")
            return []

    if not isinstance(findings, list):
        return []

    matches: list[LLMMatch] = []
    for item in findings:
        if not isinstance(item, dict):
            continue

        pii_text = item.get("text", "")
        pii_type_str = item.get("type", "CUSTOM")

        if not pii_text:
            continue

        try:
            pii_type = PIIType(pii_type_str)
        except ValueError:
            pii_type = PIIType.CUSTOM

        # Fuzzy find in source text
        local_idx = _fuzzy_find(pii_text, source_text)
        if local_idx is None:
            logger.debug(f"LLM PII not found (even fuzzy): '{pii_text}'")
            continue

        # Use the actual text from the source (not the LLM's version)
        resolved_text = source_text[local_idx : local_idx + len(pii_text)]

        matches.append(LLMMatch(
            start=global_offset + local_idx,
            end=global_offset + local_idx + len(pii_text),
            text=resolved_text,
            pii_type=pii_type,
            confidence=0.75,
        ))

    return matches


def _deduplicate(matches: list[LLMMatch]) -> list[LLMMatch]:
    """Remove duplicate matches from overlapping chunks."""
    if not matches:
        return []

    matches = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))
    deduped: list[LLMMatch] = [matches[0]]

    for m in matches[1:]:
        prev = deduped[-1]
        if m.start < prev.end:
            # Overlapping — keep higher confidence or longer span
            if m.confidence > prev.confidence or (m.end - m.start) > (prev.end - prev.start):
                deduped[-1] = m
        else:
            deduped.append(m)

    return deduped
