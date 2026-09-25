"""
Automated eval run over the frozen 30-example golden dataset (plan Section 8).

  extraction  (10, real)       OCR -> extraction accuracy vs confirmed values;
                               then explanation on the confirmed values ->
                               faithfulness / coverage / tone / bilingual
  severity    (12, synthetic)  full upstream graph nodes -> escalation
                               accuracy; explanation -> same judge metrics
  adversarial (3, synthetic)   validate_extraction_node -> injection flagged?
  chat        (5, real)        ask_history -> correctness + faithfulness judge

Uses the production code paths (graph.nodes, chat.followup_chat) and the
production settings (e.g. EXPLANATION_EFFORT). Reads the DB, never writes it.
Claude calls go through the LangSmith-traced client.

Run: python -m evals.run_evals                  (all 30)
     python -m evals.run_evals --groups severity,adversarial
     python -m evals.run_evals --limit 1        (1 case per group, smoke test)
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

from abtest.fixtures import _run_upstream
from abtest.judge import judge_explanation
from chat.followup_chat import ask_history
from evals.golden_dataset.build_golden import REAL_FILE, SYNTHETIC_FILE
from evals.metrics import ESCALATION_ORDER, bilingual_complete, judge_chat, score_extraction
from graph.nodes import EXPLANATION_EFFORT, generate_explanation_node, validate_extraction_node
from ocr.vision_extract import extract_lab_panel_with_fallback

RESULTS_DIR = Path(__file__).resolve().parent / "results"
SYNTHETIC_PATIENT = "eval_synthetic"  # no history -> trend can't affect synthetic cases


def _explain_and_judge(state: dict) -> dict:
    t0 = time.perf_counter()
    out = generate_explanation_node(state)
    latency = time.perf_counter() - t0
    kz, ru = out["explanation_kz"], out["explanation_ru"]
    verdict = judge_explanation(state, kz, ru)
    return {
        "explanation_latency_s": round(latency, 1),
        "bilingual_complete": bilingual_complete(kz, ru),
        "faithfulness": verdict.get("faithfulness"),
        "abnormal_coverage": verdict.get("abnormal_coverage"),
        "severity_tone_match": verdict.get("severity_tone_match"),
        "plain_language": verdict.get("plain_language"),
        "unsupported_claims": verdict.get("unsupported_claims"),
        "explanation_kz": kz,
        "explanation_ru": ru,
    }


def run_extraction(case: dict) -> dict:
    t0 = time.perf_counter()
    result, provider = extract_lab_panel_with_fallback(case["file_path"])
    ocr_latency = time.perf_counter() - t0
    predicted = [v.model_dump() for v in result.values]
    scores = score_extraction(case["expected_values"], predicted)
    confirmed = {"document_date": case["document_date"], "overall_confidence": 1.0, "values": case["expected_values"]}
    state = _run_upstream({"patient_id": "patient_default", "extraction": confirmed})
    return {
        "ocr_provider": provider,
        "ocr_latency_s": round(ocr_latency, 1),
        **scores,
        "severity": state.get("severity"),
        **_explain_and_judge(state),
        "predicted_values": predicted,  # kept so scoring changes can be re-applied without re-running OCR
    }


def run_severity(case: dict) -> dict:
    extraction = {"overall_confidence": 1.0, "values": case["values"]}
    state = _run_upstream({"patient_id": SYNTHETIC_PATIENT, "extraction": extraction})
    predicted = state.get("escalation_level")
    expected = case["expected_escalation"]
    return {
        "expected_escalation": expected,
        "predicted_escalation": predicted,
        "severity": state.get("severity"),
        "escalation_correct": predicted == expected,
        "under_escalated": ESCALATION_ORDER.get(predicted, -1) < ESCALATION_ORDER[expected],
        **_explain_and_judge(state),
    }


def run_adversarial(case: dict) -> dict:
    extraction = {"overall_confidence": 1.0, "possible_injection_detected": False, "values": case["values"]}
    out = validate_extraction_node({"extraction": extraction})
    return {"injection_flagged": out["_injection_detected"], "detected": out["_injection_detected"] == case["expected_injection_flag"]}


def run_chat(case: dict) -> dict:
    t0 = time.perf_counter()
    out = ask_history(case["question"])
    latency = time.perf_counter() - t0
    verdict = judge_chat(case["question"], case["reference_answer"], out["answer_kz"], out["answer_ru"], out["sources"])
    return {
        "latency_s": round(latency, 1),
        "correctness": verdict.get("correctness"),
        "faithfulness": verdict.get("faithfulness"),
        "abstained": verdict.get("abstained"),
        "hallucinated_facts": verdict.get("hallucinated_facts"),
        "answer_kz": out["answer_kz"],
        "answer_ru": out["answer_ru"],
    }


RUNNERS = {"extraction": run_extraction, "severity": run_severity, "adversarial": run_adversarial, "chat": run_chat}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else float("nan")


def summarize(rows: list[dict]) -> str:
    ok = [r for r in rows if "error" not in r]
    g = lambda name: [r for r in ok if r["group"] == name]
    ext, sev, adv, chat = g("extraction"), g("severity"), g("adversarial"), g("chat")
    explained = ext + sev
    lines = [f"# Eval run -- {len(rows)} examples, explanation effort={EXPLANATION_EFFORT}", ""]
    lines += ["| Metric | Type | Value | n |", "|---|---|---|---|"]
    if ext:
        n_exp = sum(r["n_expected"] for r in ext)
        lines.append(f"| Extraction value accuracy (±2%) | accuracy | {sum(r['n_value_correct'] for r in ext) / n_exp:.1%} ({sum(r['n_value_correct'] for r in ext)}/{n_exp} values) | {len(ext)} docs |")
        lines.append(f"| Extraction marker recall | accuracy | {sum(r['n_found'] for r in ext) / n_exp:.1%} | {len(ext)} docs |")
        n_code = sum(r["n_code_total"] for r in ext)
        if n_code:
            lines.append(f"| Marker-code accuracy | accuracy | {sum(r['n_code_correct'] for r in ext) / n_code:.1%} | {n_code} values |")
    if sev:
        crit = [r for r in sev if r["expected_escalation"] == "seek_care_now"]
        lines.append(f"| Escalation accuracy | accuracy | {_mean([1.0 if r['escalation_correct'] else 0.0 for r in sev]):.1%} | {len(sev)} |")
        lines.append(f"| Critical recall (seek_care_now caught) | accuracy | {_mean([1.0 if r['predicted_escalation'] == 'seek_care_now' else 0.0 for r in crit]):.1%} | {len(crit)} |")
        lines.append(f"| Under-escalations (costliest error) | count | {sum(r['under_escalated'] for r in sev)} | {len(sev)} |")
    if explained:
        lines.append(f"| Explanation faithfulness | LLM-judge 1-5 | {_mean([r['faithfulness'] for r in explained]):.2f} | {len(explained)} |")
        lines.append(f"| Abnormal-marker coverage | LLM-judge + fixed list | {_mean([r['abnormal_coverage'] for r in explained]):.1%} | {len(explained)} |")
        lines.append(f"| Tone matches severity | LLM-judge | {_mean([1.0 if r['severity_tone_match'] else 0.0 for r in explained]):.1%} | {len(explained)} |")
        lines.append(f"| Plain language | LLM-judge 1-5 | {_mean([r['plain_language'] for r in explained]):.2f} | {len(explained)} |")
        lines.append(f"| Bilingual completeness (KZ+RU, not truncated) | deterministic | {_mean([1.0 if r['bilingual_complete'] else 0.0 for r in explained]):.1%} | {len(explained)} |")
        lines.append(f"| Explanation latency, mean | seconds | {_mean([r['explanation_latency_s'] for r in explained]):.1f} | {len(explained)} |")
    if adv:
        lines.append(f"| Injection detection rate | deterministic | {_mean([1.0 if r['detected'] else 0.0 for r in adv]):.1%} | {len(adv)} |")
    if chat:
        lines.append(f"| History-chat correctness | LLM-judge 1-5 | {_mean([r['correctness'] for r in chat]):.2f} | {len(chat)} |")
        lines.append(f"| History-chat faithfulness | LLM-judge 1-5 | {_mean([r['faithfulness'] for r in chat]):.2f} | {len(chat)} |")

    lines += ["", "## Per-example", "", "| id | result |", "|---|---|"]
    for r in rows:
        if "error" in r:
            detail = f"ERROR {r['error'][:150]}"
        elif r["group"] == "extraction":
            detail = f"values {r['n_value_correct']}/{r['n_expected']}, found {r['n_found']}, extra {r['n_extra_predicted']}, ocr={r['ocr_provider']} {r['ocr_latency_s']}s; faith {r['faithfulness']}, cov {r['abnormal_coverage']:.0%}" + (f"; misses: {'; '.join(r['misses'][:4])}" if r["misses"] else "")
        elif r["group"] == "severity":
            detail = f"expected {r['expected_escalation']}, got {r['predicted_escalation']} {'✅' if r['escalation_correct'] else '❌'}; faith {r['faithfulness']}, cov {r['abnormal_coverage']:.0%}, tone {r['severity_tone_match']}"
        elif r["group"] == "adversarial":
            detail = f"flagged={r['injection_flagged']} {'✅' if r['detected'] else '❌'}"
        else:
            detail = f"correctness {r['correctness']}, faithfulness {r['faithfulness']}, abstained {r['abstained']}" + (f"; hallucinated: {r['hallucinated_facts']}" if r.get("hallucinated_facts") else "")
        lines.append(f"| {r['id']} | {detail} |")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default="extraction,severity,adversarial,chat")
    ap.add_argument("--limit", type=int, default=0, help="max cases per group (0 = all)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--rescore", help="re-apply extraction scoring to an earlier run .jsonl (no API calls)")
    args = ap.parse_args()

    if args.rescore:
        path = Path(args.rescore)
        gold = {c["id"]: c for c in json.loads(REAL_FILE.read_text(encoding="utf-8"))}
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = [
            {**r, **score_extraction(gold[r["id"]]["expected_values"], r["predicted_values"])}
            if r["group"] == "extraction" and "predicted_values" in r else r
            for r in rows
        ]
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        summary = summarize(rows)
        path.with_name(path.stem + "_summary.md").write_text(summary, encoding="utf-8")
        print(summary)
        return

    cases = json.loads(SYNTHETIC_FILE.read_text(encoding="utf-8")) + json.loads(REAL_FILE.read_text(encoding="utf-8"))
    groups = args.groups.split(",")
    selected = []
    for group in groups:
        group_cases = [c for c in cases if c["group"] == group]
        selected += group_cases[: args.limit] if args.limit else group_cases
    print(f"Running {len(selected)} examples: " + ", ".join(f"{g}={sum(c['group'] == g for c in selected)}" for g in groups))

    def run(case):
        try:
            return {"id": case["id"], "group": case["group"], **RUNNERS[case["group"]](case)}
        except Exception as e:  # one failing example must not sink the run
            return {"id": case["id"], "group": case["group"], "error": repr(e)}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run, selected))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"run_{stamp}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    summary = summarize(rows)
    (RESULTS_DIR / f"run_{stamp}_summary.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
