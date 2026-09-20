"""
PII scrubbing for narrative documents (discharge summaries, imaging reports).

Plan Section 10: must run BEFORE persistence/embedding, not just before display
-- PII baked into the patient_history Chroma collection can't be un-embedded
later. Built ahead of its Day 4 graph-integration slot because it was needed
immediately for anonymizing real documents into the golden dataset (Day 2).

Design choice (documented for the defense "why not just Presidio out of the
box" question): Presidio's default PERSON/NER recognizer relies on a spaCy
English language model and does not reliably detect Cyrillic (Russian/Kazakh)
names -- verified during this build by testing it against a real discharge
summary. For THIS narrow, highly structured document type (Kazakhstani
medical records with predictable labeled fields), label-anchored regex is
both more reliable and independently testable/auditable than relying on
generic NER for a language it wasn't trained for. Presidio is layered on top
as a supplementary pass for the patterns it IS good at cross-language
(phone numbers, email addresses) -- combining "Presidio + custom KZ/RU regex"
exactly as scoped in the plan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

REDACTION_TOKEN = "[REDACTED]"


@dataclass
class ScrubResult:
    text: str
    redaction_types_found: list[str] = field(default_factory=list)


# --- Label-anchored patterns (highest confidence: a known field label
# followed by the value to redact, up to end of line or a stopping token) ---

_LABEL_PATTERNS: list[tuple[str, str]] = [
    ("patient_name", r"(?:Пациент(?:ка)?|ТАӘ\s*\(ФИО\)|ФИО)\s*:\s*([^\n,]+)"),
    ("dob", r"(\d{2}[./]\d{2}[./]\d{4})\s*г\.?\s*р\.?"),
    ("dob_labeled", r"(?:Туған\s*к[үu]ні|Дата\s*рождения)\s*(?:\(Дата\s*рождения\))?\s*:\s*([^\n,]+)"),
    ("iin", r"(?:ЖСН|ИИН)\s*(?:\(ИИН\))?\s*:\s*(\d{10,12})"),
    ("address", r"(?:Мекен-жайы|Адрес)\s*(?:\(Адрес\))?\s*:\s*([^\n]+)"),
    ("phone_labeled", r"(?:Телефон|Тел\.?)\s*:\s*([\d\s()+-]{7,})"),
    (
        "staff_labeled",
        r"(?:Лечащий\s*врач|Хирург|Врач|Дәрігер|Биотехнолог[и]?)\s*:\s*"
        r"([А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]{2,}(?:(?:\s+[А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]{2,}){1,2}|\s+[А-ЯӘҒҚҢӨҰҮҺІ]\.\s?[А-ЯӘҒҚҢӨҰҮҺІ]?\.)"
        # comma-continuation: a label can introduce more than one name, e.g.
        # "Биотехнологи: Темиреев Д.Б., Абдульманова А.В." -- caught during
        # testing, where an earlier version of this pattern silently dropped
        # every name after the first one in such a list.
        r"(?:,\s*[А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]{2,}(?:(?:\s+[А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]{2,}){1,2}|\s+[А-ЯӘҒҚҢӨҰҮҺІ]\.\s?[А-ЯӘҒҚҢӨҰҮҺІ]?\.))*)",
    ),
]

# Contextual staff-name pattern: only redacts a name-shaped sequence when it
# appears near a role word (директор/руководитель/врач/доктор/гепатолог/
# хирург/биотехнолог, any grammatical case via \w*), rather than matching
# ANY two consecutive capitalized words anywhere in the text.
#
# An earlier, context-free version of this pattern (bare "Surname И.О." /
# "Surname Firstname Patronymic" shape, matched anywhere) was tried during
# testing on the real discharge summary and produced false positives on
# capitalized drug/brand names that happen to share the shape -- "Гептрал"
# following a capitalized sentence-starter, "Сироп Дюфалак", "Кальцемин
# Адванс". Anchoring to nearby role words fixes that while still catching
# names in grammatical cases the exact-label patterns above miss (e.g.
# "лечащего врача Клименко А.В." -- genitive case, not matched by the
# nominative-only LABEL_PATTERNS "Лечащий\s*врач" entry).
_NAME_SHAPE = (
    r"[А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]{3,}"
    r"(?:(?:\s+[А-ЯӘҒҚҢӨҰҮҺІ][а-яәғқңөұүһі]{2,}){1,2}"
    r"|\s+[А-ЯӘҒҚҢӨҰҮҺІ]\.\s?[А-ЯӘҒҚҢӨҰҮҺІ]?\.)"
)
_ROLE_CONTEXT_WORDS = r"(?:директор\w*|руководител\w*|врач\w*|доктор\w*|консультац\w*|гепатолог\w*|хирург\w*|терапевт\w*|биотехнолог\w*)"
# Trailing (?:,\s*NAME)* handles a comma-separated list of names after one
# role word (e.g. "Биотехнологи: Темиреев Д.Б., Абдульманова А.В.") -- an
# earlier version only captured the first name in such a list, verified
# against this same real document during testing.
_CONTEXTUAL_STAFF_PATTERN = _ROLE_CONTEXT_WORDS + r"[^.\n]{0,40}?(" + _NAME_SHAPE + r"(?:,\s*" + _NAME_SHAPE + r")*)"

# Standalone 12-digit number, unlabeled -- fallback IIN catch. Deliberately
# requires exactly 12 digits (KZ IIN length) to minimize false positives
# against lab values, which almost never run that many consecutive digits.
_BARE_IIN_PATTERN = r"\b\d{12}\b"


def scrub_narrative_text(text: str) -> ScrubResult:
    found: list[str] = []
    result = text

    for name, pattern in _LABEL_PATTERNS:
        def _replace(m: re.Match, name=name) -> str:
            found.append(name)
            # Keep the label, redact only the captured value.
            return m.group(0).replace(m.group(1), REDACTION_TOKEN)

        result = re.sub(pattern, _replace, result, flags=re.IGNORECASE)

    def _replace_staff(m: re.Match) -> str:
        found.append("staff_name_contextual")
        return m.group(0).replace(m.group(1), REDACTION_TOKEN)

    # NOTE: deliberately NOT case-insensitive here -- the name-shape part of
    # this pattern depends on the uppercase/lowercase Cyrillic distinction to
    # recognize "capitalized word" shapes; IGNORECASE would collapse that and
    # make it match ordinary lowercase text too. Role words are written in
    # lowercase below to match their most common mid-sentence form.
    result = re.sub(_CONTEXTUAL_STAFF_PATTERN, _replace_staff, result)

    def _replace_iin(m: re.Match) -> str:
        found.append("bare_iin_like_number")
        return REDACTION_TOKEN

    result = re.sub(_BARE_IIN_PATTERN, _replace_iin, result)

    return ScrubResult(text=result, redaction_types_found=found)


def scrub_with_presidio(text: str) -> ScrubResult:
    """Supplementary pass for patterns Presidio handles well cross-language
    (phone numbers, emails, URLs) -- run AFTER scrub_narrative_text, not
    instead of it. Optional: falls back to a no-op if presidio isn't
    importable/configured in this environment."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
    except ImportError:
        return ScrubResult(text=text, redaction_types_found=[])

    analyzer = AnalyzerEngine()
    results = analyzer.analyze(text=text, language="en", entities=["PHONE_NUMBER", "EMAIL_ADDRESS", "URL"])
    if not results:
        return ScrubResult(text=text, redaction_types_found=[])

    anonymizer = AnonymizerEngine()
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return ScrubResult(text=anonymized.text, redaction_types_found=[r.entity_type for r in results])


def scrub(text: str) -> ScrubResult:
    """Full pipeline: label-anchored regex (primary) + Presidio (supplementary)."""
    first_pass = scrub_narrative_text(text)
    second_pass = scrub_with_presidio(first_pass.text)
    return ScrubResult(
        text=second_pass.text,
        redaction_types_found=first_pass.redaction_types_found + second_pass.redaction_types_found,
    )
