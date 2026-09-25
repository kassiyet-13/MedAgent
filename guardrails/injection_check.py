"""
Deterministic, keyword/regex-based prompt-injection check -- deliberately
independent of the OCR model's own `possible_injection_detected` self-report
(ocr/schema.py). The model's self-report can miss things (same trust
problem as the confidence-score finding from Day 2); this is a second,
non-LLM layer that can't be talked out of flagging something by the
injected text itself.

Plan Section 10: OCR-extracted text is treated as untrusted data, never
instructions. This check runs on any free text pulled from a document
(marker names/notes on the lab path, the full narrative text on the
narrative path) before it's trusted downstream.
"""
from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    r"\bignore\s+(all\s+)?(previous|above|prior)\s+instructions?\b",
    r"\bdisregard\s+(all\s+)?(previous|above|prior)\b",
    r"\byou\s+are\s+now\b",
    r"\bnew\s+instructions?\s*:",
    r"\bsystem\s*:\s*",
    r"\bassistant\s*:\s*",
    r"\b(reveal|print|show)\s+(your\s+)?(system\s+)?prompt\b",
    r"\bигнорируй\s+(все\s+)?(предыдущие|предыдущий)\s+(инструкции|указания)\b",
    r"\bновые\s+инструкции\s*:",
    r"\bты\s+теперь\b",
    r"\b(забудь|не\s+обращай\s+внимания\s+на)\s+(все\s+)?(предыдущие\s+)?(инструкции|указания)\b",
    # Kazakh -- the eval's adversarial set (evals/golden_dataset, adv_03)
    # showed the single KZ pattern below missed an ordinary "ignore the
    # previous instructions" phrasing. Matches the verb family (елеме/
    # ескерме/орындама + suffixes) after any form of "нұсқау", and
    # "previous instructions" itself.
    r"\bсенің\s+жаңа\s+н[ұu]сқауың\b",
    r"\bн[ұu]сқау\w*\s+(елеме|ескерме|орындама)\w*",
    r"\b(алдыңғы|бұрынғы|жоғарыдағы)\s+(барлық\s+)?н[ұu]сқау\w*",
    r"\bжаңа\s+н[ұu]сқау\w*\s*:",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def check_for_injection(text: str) -> tuple[bool, list[str]]:
    """Returns (flagged, matched_patterns). Deliberately conservative
    (pattern list, not ML) -- false positives here just mean an extra
    human-confirm pause, which is cheap; false negatives are the real risk
    to avoid, so patterns cover both English and RU/KZ phrasing."""
    matched = []
    for pattern in _COMPILED:
        if pattern.search(text):
            matched.append(pattern.pattern)
    return (len(matched) > 0, matched)
