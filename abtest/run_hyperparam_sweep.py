"""
Hyperparameter experiment (plan Section 9, mandatory): `effort` for
generate_explanation_node.

The plan originally specified a temperature sweep (0 / 0.3 / 0.7), but the
generator model, Claude Sonnet 5, rejects temperature/top_p with a 400 and
runs adaptive thinking by default -- `output_config.effort` (low / medium /
high) is the sampling-side knob it actually exposes, and it directly trades
thinking depth against latency and cost. Real-usage trigger: the
"Растаймын" step felt slow, and this node is ~all of that wait.

Everything except effort is held fixed: same real confirmed lab panels,
same upstream state (abtest/fixtures.py), same production prompt
(graph.nodes.build_explanation_prompt), same max_tokens.

Run:  python -m abtest.run_hyperparam_sweep            (6 fixtures x 3 efforts)
      python -m abtest.run_hyperparam_sweep --smoke    (1 fixture, low only)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from abtest.fixtures import RESULTS_DIR, load_fixtures
from abtest.judge import judge_explanation
from graph.nodes import CLAUDE_MODEL, build_explanation_prompt, parse_explanation
from llm_clients import get_traced_anthropic_client

# USD per 1M tokens, Claude Sonnet 5 list price. Thinking tokens are billed
# as output and are included in usage.output_tokens.
PRICE_IN, PRICE_OUT = 2.00, 10.00
MAX_TOKENS = 6000  # same as production


def run_one(fixture: dict, effort: str) -> dict:
    prompt = build_explanation_prompt(fixture)
    client = get_traced_anthropic_client()
    t0 = time.perf_counter()
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    )
    latency = time.perf_counter() - t0
    text = "".join(b.text for b in resp.content if b.type == "text")
    kz, ru = parse_explanation(text, resp.stop_reason)
    truncated = resp.stop_reason == "max_tokens"
    verdict = judge_explanation(fixture, kz, ru)
    return {
        "fixture_id": fixture["fixture_id"],
        "severity": fixture.get("severity"),
        "effort": effort,
        "latency_s": round(latency, 1),
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "visible_chars": len(kz) + len(ru),
        "cost_usd": (resp.usage.input_tokens * PRICE_IN + resp.usage.output_tokens * PRICE_OUT) / 1e6,
        "stop_reason": resp.stop_reason,
        "bilingual_complete": bool(kz.strip()) and bool(ru.strip()) and not truncated,
        **{k: verdict.get(k) for k in (
            "faithfulness", "abnormal_coverage", "severity_tone_match", "plain_language",
            "ru_kz_consistent", "unsupported_claims", "judge_cost_usd",
        )},
        "explanation_kz": kz,
        "explanation_ru": ru,
    }


def summarize(rows: list[dict], efforts: list[str]) -> str:
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return statistics.mean(xs) if xs else float("nan")

    header = (
        "| effort | n | latency s (mean / max) | output tokens | cost $/call | faithfulness (1-5) "
        "| abnormal coverage | tone match | plain language (1-5) | bilingual complete |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [header]
    for effort in efforts:
        r = [x for x in rows if x["effort"] == effort and "error" not in x]
        if not r:
            continue
        lines.append(
            f"| {effort} | {len(r)} "
            f"| {mean([x['latency_s'] for x in r]):.1f} / {max(x['latency_s'] for x in r):.1f} "
            f"| {mean([x['output_tokens'] for x in r]):.0f} "
            f"| {mean([x['cost_usd'] for x in r]):.4f} "
            f"| {mean([x['faithfulness'] for x in r]):.2f} "
            f"| {mean([x['abnormal_coverage'] for x in r]):.0%} "
            f"| {mean([1.0 if x['severity_tone_match'] else 0.0 for x in r]):.0%} "
            f"| {mean([x['plain_language'] for x in r]):.2f} "
            f"| {mean([1.0 if x['bilingual_complete'] else 0.0 for x in r]):.0%} |"
        )
    errors = [x for x in rows if "error" in x]
    if errors:
        lines.append(f"\nErrors: {len(errors)} -- " + "; ".join(f"{e['fixture_id']}/{e['effort']}: {e['error']}" for e in errors))
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--efforts", default="low,medium,high")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--rebuild-fixtures", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="1 fixture, effort=low -- pipeline check")
    ap.add_argument("--rejudge", help="re-score an earlier results .jsonl with the current judge (no generation calls)")
    args = ap.parse_args()

    if args.rejudge:
        raw_path = Path(args.rejudge)
        rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        fixtures_by_id = {f["fixture_id"]: f for f in load_fixtures(len({r["fixture_id"] for r in rows}))}

        def rescore(row):
            if "error" in row:
                return row
            verdict = judge_explanation(fixtures_by_id[row["fixture_id"]], row["explanation_kz"], row["explanation_ru"])
            return {**row, **{k: verdict.get(k) for k in (
                "faithfulness", "abnormal_coverage", "severity_tone_match", "plain_language",
                "ru_kz_consistent", "unsupported_claims", "judge_cost_usd",
            )}}

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(rescore, rows))
        raw_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        efforts_seen = [e for e in ("low", "medium", "high") if any(r["effort"] == e for r in rows)]
        table = summarize(rows, efforts_seen)
        raw_path.with_name(raw_path.stem + "_summary.md").write_text(table, encoding="utf-8")
        print(table)
        return

    n, efforts = (1, ["low"]) if args.smoke else (args.n, args.efforts.split(","))
    fixtures = load_fixtures(max(n, 1), rebuild=args.rebuild_fixtures)[:n]
    print(f"Fixtures: {[(f['fixture_id'], f.get('severity')) for f in fixtures]}")

    def safe(fx, eff):
        try:
            return run_one(fx, eff)
        except Exception as e:  # keep the other runs going; reported in the summary
            return {"fixture_id": fx["fixture_id"], "effort": eff, "error": repr(e)}

    jobs = [(fx, eff) for fx in fixtures for eff in efforts]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda j: safe(*j), jobs))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / f"hyperparam_{stamp}.jsonl"
    raw_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    table = summarize(rows, efforts)
    (RESULTS_DIR / f"hyperparam_{stamp}_summary.md").write_text(table, encoding="utf-8")
    total = sum(r.get("cost_usd", 0) + (r.get("judge_cost_usd") or 0) for r in rows)
    print(table)
    print(f"\nTotal spend: ${total:.3f}  |  raw: {raw_path}")


if __name__ == "__main__":
    main()
