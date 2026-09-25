"""
LLM-as-judge for generated explanations (plan Section 8, metric 3 & 4).

Judge is OpenAI gpt-4o-mini -- deliberately a different provider than the
generator under test (Claude), to avoid a model grading its own family's
output. For the Claude-vs-GPT-4o A/B this is not neutral either (same family
as one arm), which is why abnormal-marker coverage is also checked against a
fixed, deterministic expected list rather than left to the judge's opinion.
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

# Upgraded from gpt-4o-mini: in the first full eval run, mini gave a
# history-chat answer 5/5 "correct" although it stated the wrong spleen size
# and claimed the latest ultrasound didn't report one. A judge that misses
# that can't be trusted on faithfulness either.
JUDGE_MODEL = "gpt-4o"
# USD per 1M tokens (OpenAI list price) -- only used for cost reporting.
JUDGE_PRICE_IN, JUDGE_PRICE_OUT = 2.50, 10.00

JUDGE_PROMPT = """You are grading a patient-facing explanation of lab results written
by an AI assistant for a patient with primary biliary cholangitis / cirrhosis.
The explanation is given in Kazakh (KZ) and Russian (RU).

SOURCE FACTS (the only information the explanation may rely on):
Lab values (with normal ranges where known):
{values}

Deterministic severity assessment: {severity}
Markers outside their normal range (the explanation MUST mention each): {out_of_range}

Retrieved clinical guideline excerpts:
{rag}

EXPLANATION TO GRADE:
KZ: {kz}

RU: {ru}

Return a JSON object with exactly these keys:
- "faithfulness": integer 1-5. 5 = every factual claim (values, directions,
  what a marker means, advice) is supported by the SOURCE FACTS or is general
  well-established medical knowledge; 1 = invents values, diagnoses or
  contradicts the source. Judge KZ and RU together.
- "unsupported_claims": list of short strings, each an unsupported or wrong
  claim (empty list if none).
- "abnormal_mentioned": list of the marker codes from the out-of-range list
  that the explanation explicitly mentions (by name, abbreviation or clear
  description, in any language) in at least one language. Copy each code
  EXACTLY as written before the parentheses in that list (e.g. "PLATELETS",
  not "PLT").
- "severity_tone_match": true if the tone/urgency matches the severity
  assessment (critical -> urges prompt medical contact; worsening -> advises
  seeing a doctor; stable/improving -> reassuring, routine monitoring).
- "plain_language": integer 1-5, how understandable it is for a family
  member with no medical background (5 = very clear, terms explained).
- "ru_kz_consistent": true if the KZ and RU versions convey the same content.
"""


def judge_client() -> OpenAI:
    """gpt-4o on this account has a 30k tokens/min limit and one judge prompt
    is ~3k tokens, so parallel eval workers hit 429 quickly. The SDK's retry
    honours the retry-after header; the default 2 retries was not enough."""
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=10)


def _values_text(state: dict) -> str:
    ranges = state.get("reference_ranges", {})
    lines = []
    for v in state["extraction"]["values"]:
        shown = v.get("value") if v.get("value") is not None else v.get("value_text")
        r = ranges.get(v.get("marker_code")) or {}
        rng = f" (normal {r['normal_low']}-{r['normal_high']})" if r.get("normal_low") is not None and r.get("normal_high") is not None else ""
        lines.append(f"- {v.get('marker_name_as_written')} [{v.get('marker_code')}]: {shown} {v.get('unit') or ''}{rng}")
    return "\n".join(lines)


def judge_explanation(state: dict, kz: str, ru: str) -> dict:
    expected = state.get("_out_of_range_markers") or []
    # Code alone was not enough: first run, the judge answered "PLT" for
    # PLATELETS and a clearly-mentioned marker scored as missed. Give it the
    # names as written on the report, and match codes case-insensitively.
    names = {v.get("marker_code"): v.get("marker_name_as_written") for v in state["extraction"]["values"]}
    rag = "\n\n".join(f"[{r.get('source_title')}] {r.get('chunk_text')}" for r in state.get("rag_context", []))
    prompt = JUDGE_PROMPT.format(
        values=_values_text(state),
        severity=state.get("severity"),
        out_of_range=", ".join(f"{c} ({names.get(c) or c})" for c in expected) or "(none)",
        rag=rag or "(none)",
        kz=kz,
        ru=ru,
    )
    client = judge_client()
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    verdict = json.loads(resp.choices[0].message.content)
    mentioned = {str(c).upper() for c in verdict.get("abnormal_mentioned") or []} & {c.upper() for c in expected}
    verdict["abnormal_coverage"] = (len(mentioned) / len(expected)) if expected else 1.0
    verdict["judge_cost_usd"] = (
        resp.usage.prompt_tokens * JUDGE_PRICE_IN + resp.usage.completion_tokens * JUDGE_PRICE_OUT
    ) / 1e6
    return verdict
