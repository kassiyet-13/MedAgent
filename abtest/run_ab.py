"""
A/B test (plan Section 9): Claude Sonnet 5 vs GPT-4o as the generator in
generate_explanation_node.

Held fixed: the inputs (the 22 explanation cases of the golden dataset -- 10
real confirmed panels + 12 synthetic severity cases -- run once through the
upstream graph nodes and cached), the exact production prompt
(graph.nodes.build_explanation_prompt), max_tokens, parsing, and the judge.
Only the generator changes.

  A = claude-sonnet-5, effort=medium (production setting, see EVALS.md)
  B = gpt-4o, temperature=0.3

Judge caveat: the judge is gpt-4o, i.e. the same model as arm B, so any
self-preference bias favours B. Coverage of out-of-range markers is checked
against a fixed deterministic list, and Kazakh-script share is measured
without any LLM, so part of the comparison doesn't depend on the judge.

Run: python -m abtest.run_ab            (22 cases x 2 arms)
     python -m abtest.run_ab --limit 1  (smoke)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from abtest.fixtures import RESULTS_DIR, _run_upstream
from abtest.judge import judge_client, judge_explanation
from evals.golden_dataset.build_golden import REAL_FILE, SYNTHETIC_FILE
from evals.metrics import bilingual_complete
from graph.nodes import CLAUDE_MODEL, EXPLANATION_EFFORT, build_explanation_prompt, parse_explanation
from llm_clients import get_traced_anthropic_client

AB_FIXTURES_FILE = RESULTS_DIR / "ab_fixtures.json"
MAX_TOKENS = 6000
GPT_MODEL, GPT_TEMPERATURE = "gpt-4o", 0.3
# USD per 1M tokens, list prices.
PRICES = {"claude": (2.00, 10.00), "gpt4o": (2.50, 10.00)}
_KZ_LETTERS = re.compile(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]")
_CYRILLIC_WORD = re.compile(r"\b[а-яёәғқңөұүһіА-ЯЁӘҒҚҢӨҰҮҺІ]+\b")


def kz_word_share(text: str) -> float:
    """Share of Cyrillic words containing a Kazakh-only letter -- a no-LLM
    proxy for "is the KZ version actually Kazakh, not Russian with a few
    Kazakh words". Not a quality score; used to compare the two arms."""
    words = _CYRILLIC_WORD.findall(text)
    return sum(bool(_KZ_LETTERS.search(w)) for w in words) / len(words) if words else 0.0


def load_ab_fixtures(rebuild: bool = False) -> list[dict]:
    if AB_FIXTURES_FILE.exists() and not rebuild:
        return json.loads(AB_FIXTURES_FILE.read_text(encoding="utf-8"))
    cases = json.loads(REAL_FILE.read_text(encoding="utf-8")) + json.loads(SYNTHETIC_FILE.read_text(encoding="utf-8"))
    fixtures = []
    for c in cases:
        if c["group"] == "extraction":
            extraction = {"document_date": c["document_date"], "overall_confidence": 1.0, "values": c["expected_values"]}
            state = _run_upstream({"patient_id": "patient_default", "extraction": extraction})
        elif c["group"] == "severity":
            state = _run_upstream({"patient_id": "eval_synthetic", "extraction": {"overall_confidence": 1.0, "values": c["values"]}})
        else:
            continue
        fixtures.append({"fixture_id": c["id"], **state})
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    AB_FIXTURES_FILE.write_text(json.dumps(fixtures, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return fixtures


def generate(arm: str, prompt: str) -> tuple[str, str | None, int, int]:
    """Returns (text, stop_reason, input_tokens, output_tokens)."""
    if arm == "claude":
        resp = get_traced_anthropic_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EXPLANATION_EFFORT},
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return text, resp.stop_reason, resp.usage.input_tokens, resp.usage.output_tokens
    resp = judge_client().chat.completions.create(  # same retrying OpenAI client
        model=GPT_MODEL,
        temperature=GPT_TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    stop = "max_tokens" if resp.choices[0].finish_reason == "length" else resp.choices[0].finish_reason
    return resp.choices[0].message.content or "", stop, resp.usage.prompt_tokens, resp.usage.completion_tokens


def run_one(fixture: dict, arm: str) -> dict:
    prompt = build_explanation_prompt(fixture)
    t0 = time.perf_counter()
    text, stop, tok_in, tok_out = generate(arm, prompt)
    latency = time.perf_counter() - t0
    kz, ru = parse_explanation(text, stop)
    verdict = judge_explanation(fixture, kz, ru)
    p_in, p_out = PRICES[arm]
    return {
        "fixture_id": fixture["fixture_id"],
        "arm": arm,
        "severity": fixture.get("severity"),
        "latency_s": round(latency, 1),
        "input_tokens": tok_in,
        "output_tokens": tok_out,
        "cost_usd": (tok_in * p_in + tok_out * p_out) / 1e6,
        "bilingual_complete": bilingual_complete(kz, ru),
        "kz_word_share": round(kz_word_share(kz), 3),
        "kz_chars": len(kz),
        "ru_chars": len(ru),
        **{k: verdict.get(k) for k in (
            "faithfulness", "abnormal_coverage", "severity_tone_match", "plain_language",
            "ru_kz_consistent", "unsupported_claims",
        )},
        "explanation_kz": kz,
        "explanation_ru": ru,
    }


def summarize(rows: list[dict]) -> str:
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return statistics.mean(xs) if xs else float("nan")

    lines = [
        "| arm | n | faithfulness (1-5) | abnormal coverage | tone match | plain language (1-5) | KZ/RU consistent "
        "| bilingual complete | KZ-letter word share | latency s (mean) | cost $/call |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, label in (("claude", f"A: {CLAUDE_MODEL} (effort={EXPLANATION_EFFORT})"), ("gpt4o", f"B: {GPT_MODEL} (T={GPT_TEMPERATURE})")):
        r = [x for x in rows if x["arm"] == arm and "error" not in x]
        if not r:
            continue
        lines.append(
            f"| {label} | {len(r)} | {mean([x['faithfulness'] for x in r]):.2f} "
            f"| {mean([x['abnormal_coverage'] for x in r]):.1%} "
            f"| {mean([1.0 if x['severity_tone_match'] else 0.0 for x in r]):.0%} "
            f"| {mean([x['plain_language'] for x in r]):.2f} "
            f"| {mean([1.0 if x['ru_kz_consistent'] else 0.0 for x in r]):.0%} "
            f"| {mean([1.0 if x['bilingual_complete'] else 0.0 for x in r]):.0%} "
            f"| {mean([x['kz_word_share'] for x in r]):.1%} "
            f"| {mean([x['latency_s'] for x in r]):.1f} "
            f"| {mean([x['cost_usd'] for x in r]):.4f} |"
        )
    errors = [x for x in rows if "error" in x]
    if errors:
        lines.append(f"\nErrors: {len(errors)} -- " + "; ".join(f"{e['fixture_id']}/{e['arm']}: {e['error'][:120]}" for e in errors))
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--rebuild-fixtures", action="store_true")
    args = ap.parse_args()

    fixtures = load_ab_fixtures(rebuild=args.rebuild_fixtures)
    if args.limit:
        fixtures = fixtures[: args.limit]
    print(f"A/B on {len(fixtures)} fixtures x 2 arms")

    def safe(job):
        fx, arm = job
        try:
            return run_one(fx, arm)
        except Exception as e:
            return {"fixture_id": fx["fixture_id"], "arm": arm, "error": repr(e)}

    jobs = [(fx, arm) for fx in fixtures for arm in ("claude", "gpt4o")]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(safe, jobs))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RESULTS_DIR / f"ab_{stamp}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    table = summarize(rows)
    (RESULTS_DIR / f"ab_{stamp}_summary.md").write_text(table, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
