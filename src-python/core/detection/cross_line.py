"""Cross-line ORG boundary scanner.

Detects ORG names that span across line breaks (``\\n``) by examining
word windows around each boundary and running ORG regex patterns.
"""

from __future__ import annotations

import re

from core.detection.regex_detector import RegexMatch
from core.detection.detection_config import CROSS_LINE_WORD_WINDOW
from models.schemas import PIIType

_CROSS_LINE_WORD_WINDOW: int = CROSS_LINE_WORD_WINDOW


def _detect_cross_line_orgs(full_text: str) -> list[RegexMatch]:
    """Detect ORG names that span across line breaks.

    At each ``\\n`` boundary, extract a window of words on each side,
    join them (replacing ``\\n`` with a space — offset-safe), and run
    ORG regex patterns.  Only matches straddling the boundary are kept.

    Returns a deduplicated list of ``RegexMatch`` instances.
    """
    from core.detection.regex_patterns import PATTERNS as _PAT

    org_patterns: list[tuple[re.Pattern, PIIType, float]] = [
        (re.compile(p, f), pt, c)
        for p, pt, c, f, _langs in _PAT
        if pt == PIIType.ORG
    ]
    if not org_patterns:
        return []

    results: list[RegexMatch] = []
    wn = _CROSS_LINE_WORD_WINDOW

    for nl in re.finditer(r"\n", full_text):
        nl_pos = nl.start()

        # Window before boundary
        win_start = nl_pos
        wc = 0
        i = nl_pos - 1
        while i >= 0:
            ch = full_text[i]
            if ch == "\n":
                win_start = i + 1
                break
            if ch == " ":
                wc += 1
                if wc >= wn:
                    win_start = i + 1
                    break
            i -= 1
        else:
            win_start = 0

        # Window after boundary
        win_end = nl_pos + 1
        wc = 0
        i = nl_pos + 1
        while i < len(full_text):
            ch = full_text[i]
            if ch == "\n":
                win_end = i
                break
            if ch == " ":
                wc += 1
                if wc >= wn:
                    win_end = i
                    break
            i += 1
        else:
            win_end = len(full_text)

        window = full_text[win_start:win_end]
        if len(window.split()) < 2:
            continue

        test_text = window.replace("\n", " ")
        nl_rel = nl_pos - win_start

        for compiled_re, pii_type, conf in org_patterns:
            for m in compiled_re.finditer(test_text):
                if m.start() < nl_rel < m.end():
                    real_start = win_start + m.start()
                    real_end = win_start + m.end()
                    results.append(RegexMatch(
                        start=real_start,
                        end=real_end,
                        text=full_text[real_start:real_end],
                        pii_type=pii_type,
                        confidence=conf,
                    ))

    # Deduplicate
    seen: set[tuple[int, int]] = set()
    unique: list[RegexMatch] = []
    for r in results:
        key = (r.start, r.end)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique
