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
    # Same label WITHOUT a colon, value must be date-shaped. Found in a real
    # ultrasound report: "Пациент: ..., дата рождения 22.07.1957" -- the
    # colon-only pattern above missed it and the DOB reached the vector store.
    ("dob_inline", r"(?:Туған\s*к[үu]ні|Дата\s*рождения)\s*[-–]?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})"),
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

_DATE_LIKE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}")

# "Пациентка SURNAME И.О., ... поступила" -- no colon, and the surname is
# in capitals, so neither the "Пациент:" label pattern nor the title-case
# name shape caught it (found in a real discharge summary's body text).
# Case-SENSITIVE on purpose, like the contextual staff pattern: the name must
# start with a capital, so "Пациентка выписывается ..." is left alone.
_UPPER = "А-ЯӘҒҚҢӨҰҮҺІ"
_LOWER = "а-яәғқңөұүһі"
_PATIENT_INLINE_PATTERN = (
    rf"Пациент(?:ка|а|у|ке)?\s+("
    rf"(?:[{_UPPER}]{{2,}}|[{_UPPER}][{_LOWER}]{{2,}})"
    rf"(?:\s+[{_UPPER}]\.\s?(?:[{_UPPER}]\.)?|(?:\s+(?:[{_UPPER}]{{2,}}|[{_UPPER}][{_LOWER}]{{2,}})){{1,2}}))"
)


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

    def _replace_patient_inline(m: re.Match) -> str:
        found.append("patient_name_inline")
        return m.group(0).replace(m.group(1), REDACTION_TOKEN)

    result = re.sub(_PATIENT_INLINE_PATTERN, _replace_patient_inline, result)

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
    # Presidio's phone recognizer also fires on dotted dates + times: a real
    # discharge summary's "Дата поступления: 04.05.2023 13:08" came out as
    # "<PHONE_NUMBER>:08", destroying a clinically relevant date. Dates are
    # not PII here (dates of birth are handled by the dob patterns above).
    results = [
        r for r in results
        if not (r.entity_type == "PHONE_NUMBER" and _DATE_LIKE.search(text[r.start:r.end]))
    ]
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
