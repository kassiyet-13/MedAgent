"""
Eval metrics (plan Section 8).

Deterministic: extraction accuracy, escalation accuracy, bilingual
completeness, guardrail detection. LLM-as-judge (gpt-4o-mini, a different
provider than the Claude generator): explanation faithfulness/coverage (see
abtest/judge.py, shared with the effort experiment) and chat answers (below).
"""
from __future__ import annotations

import json
import math
import re

from abtest.judge import JUDGE_MODEL, JUDGE_PRICE_IN, JUDGE_PRICE_OUT, judge_client

REL_TOL = 0.02  # +-2% value tolerance (plan Section 8)
ESCALATION_ORDER = {"routine": 0, "see_doctor_soon": 1, "seek_care_now": 2}


def _norm(text: str | None) -> str:
    return re.sub(r"[^\w]", "", (text or "").lower())


# Qualitative results are written many ways for the same meaning -- e.g. the
# user confirmed "отр" where OCR read "отрицательно" / "отсутствует" (urine
# protein, glucose, bilirubin). Compared by meaning, not spelling.
_QUALITATIVE_SYNONYMS = {
    "neg": {"отр", "отриц", "отрицательно", "отрицательный", "отсутствует", "отсутствуют", "необнаружено",
            "необнаружены", "negative", "neg", "теріс", "жоқ"},
    "pos": {"пол", "полож", "положительно", "положительный", "обнаружено", "обнаружены", "positive", "pos", "оң"},
}


def _qualitative(text: str | None) -> str:
    n = _norm(text)
    return next((k for k, forms in _QUALITATIVE_SYNONYMS.items() if n in forms), n)


def _abbr(name: str | None) -> str:
    """Abbreviation in the last ()/[] of a name plus anything after it, e.g.
    "Лейкоциты (WBC)" -> "wbc", "Нейтрофилы (Neu)abs" -> "neuabs" (so the
    absolute and % rows of the same cell type don't collide)."""
    found = re.findall(r"[(\[]([^)\]]+)[)\]](.*)$", name or "")
    return _norm(found[-1][0] + found[-1][1]) if found else ""


def _tokens(name: str | None) -> frozenset:
    """Order-free word set: bilingual names are written both ways round
    ("Лейкоциттер/Лейкоциты" vs "Лейкоциты/Лейкоциттер")."""
    return frozenset(w for w in re.split(r"[^\w]+", (name or "").lower()) if w)


def score_extraction(expected: list[dict], predicted: list[dict]) -> dict:
    """Field-level match of OCR output against the user-confirmed values.
    Matching, first hit wins: marker_code + same abbreviation, marker_code,
    abbreviation, order-free name words, exact name. The first eval run
    matched by code or exact name only, and reported correctly-read values as
    "missing" on older panels whose confirmed rows had no code and whose
    bilingual names were written in the other order."""
    unused = list(predicted)
    found = value_ok = code_ok = code_total = 0
    misses = []
    for exp in expected:
        code, abbr, toks = exp.get("marker_code"), _abbr(exp.get("marker_name_as_written")), _tokens(exp.get("marker_name_as_written"))
        tries = []
        if code:
            tries += [lambda p: p.get("marker_code") == code and abbr and _abbr(p.get("marker_name_as_written")) == abbr,
                      lambda p: p.get("marker_code") == code]
        if abbr:
            tries.append(lambda p: _abbr(p.get("marker_name_as_written")) == abbr)
        tries += [lambda p: toks and _tokens(p.get("marker_name_as_written")) == toks,
                  lambda p: _norm(p.get("marker_name_as_written")) == _norm(exp.get("marker_name_as_written"))]
        match = next((p for t in tries for p in unused if t(p)), None)
        if match is None:
            misses.append(f"missing: {exp.get('marker_code') or exp.get('marker_name_as_written')}")
            continue
        unused.remove(match)
        found += 1
        if exp.get("marker_code"):
            code_total += 1
            code_ok += match.get("marker_code") == exp["marker_code"]
        if exp.get("value") is not None:
            ok = match.get("value") is not None and math.isclose(match["value"], exp["value"], rel_tol=REL_TOL, abs_tol=1e-9)
        else:
            ok = _qualitative(match.get("value_text")) == _qualitative(exp.get("value_text"))
        value_ok += ok
        if not ok:
            got = match.get("value") if match.get("value") is not None else match.get("value_text")
            want = exp.get("value") if exp.get("value") is not None else exp.get("value_text")
            misses.append(f"value {exp.get('marker_code') or exp.get('marker_name_as_written')}: got {got}, want {want}")
    n = len(expected)
    return {
        "n_expected": n,
        "n_found": found,
        "n_value_correct": value_ok,
        "n_code_correct": code_ok,
        "n_code_total": code_total,
        "n_extra_predicted": len(unused),
        "value_accuracy": value_ok / n if n else 1.0,
        "misses": misses,
    }


def bilingual_complete(kz: str, ru: str) -> bool:
    truncated = "не завершён" in ru or "обрезан" in ru or "толық аяқталмауы" in kz
    return bool(kz.strip()) and bool(ru.strip()) and not truncated


CHAT_JUDGE_PROMPT = """You are grading an AI assistant's answer to a patient's question
about her OWN medical documents.

QUESTION: {question}

REFERENCE ANSWER (written by a human from the patient's documents):
{reference}

SOURCES THE ASSISTANT RETRIEVED (it may only rely on these):
{sources}

ASSISTANT ANSWER:
KZ: {kz}

RU: {ru}

Return a JSON object with exactly these keys:
- "correctness": integer 1-5. First list for yourself every date, number and
  finding in the reference answer, then check each against the assistant
  answer. 5 = all key facts present and correct. If ANY key number or date
  differs from the reference, or the answer says a fact is unavailable that
  the reference contains, correctness must be 2 or lower. If the reference
  says the information is NOT in the documents, 5 = the assistant clearly
  says it has no such information, 1 = it invents a result.
- "faithfulness": integer 1-5. Is every factual claim about the patient
  supported by the SOURCES? 5 = nothing invented, 1 = invented facts.
- "hallucinated_facts": list of short strings, patient facts stated in the
  answer that are not in the sources (empty list if none).
- "abstained": true if the assistant says the information is not available.
"""


def judge_chat(question: str, reference: str, kz: str, ru: str, sources: list[dict]) -> dict:
    sources_text = "\n\n".join(
        f"[{s.get('type')}] {s.get('chunk_text', '')[:1500]}" for s in sources
    ) or "(none)"
    client = judge_client()
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": CHAT_JUDGE_PROMPT.format(
            question=question, reference=reference, sources=sources_text, kz=kz, ru=ru,
        )}],
    )
    verdict = json.loads(resp.choices[0].message.content)
    verdict["judge_cost_usd"] = (
        resp.usage.prompt_tokens * JUDGE_PRICE_IN + resp.usage.completion_tokens * JUDGE_PRICE_OUT
    ) / 1e6
    return verdict
