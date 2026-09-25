"""
Fixed inputs for the explanation-generation experiments (hyperparameter sweep
and Claude-vs-GPT-4o A/B).

Built from REAL, user-confirmed lab panels in data/medagent.db, run through
the same upstream graph nodes as production (reference ranges -> trend ->
deterministic severity -> RAG + rerank). Computed once and cached to
abtest/results/fixtures.json so every experiment arm sees byte-identical
inputs -- only the generation setting under test differs. That file holds
real patient values, which is why abtest/results/ is gitignored.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Document, LabValueRow
from data.seed_db import get_engine
from graph.edges import MAX_RAG_RETRIES, route_after_rag
from graph.nodes import (
    classify_severity_node,
    compute_trend_node,
    lookup_reference_ranges_node,
    rag_retrieve_node,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIXTURES_FILE = RESULTS_DIR / "fixtures.json"
PATIENT_ID = "patient_default"
MIN_VALUES = 5  # skip 1-2 marker slips -- too little for a meaningful explanation


def _extraction_from_db(session: Session, doc: Document) -> dict:
    rows = session.execute(
        select(LabValueRow).where(LabValueRow.document_id == doc.id, LabValueRow.user_confirmed.is_(True))
    ).scalars().all()
    return {
        "document_date": doc.document_date,
        "lab_name": doc.lab_name,
        "panel_name": doc.panel_name,
        "overall_confidence": 1.0,
        "values": [
            {
                "marker_name_as_written": r.marker_name_as_written,
                "marker_code": r.marker_code,
                "value": r.value_numeric,
                "value_text": r.value_text,
                "unit": r.unit,
                "lab_ref_low": r.lab_reported_ref_low,
                "lab_ref_high": r.lab_reported_ref_high,
                "lab_flag": r.lab_flag,
            }
            for r in rows
        ],
    }


def _run_upstream(state: dict) -> dict:
    """Same node sequence as graph/build_graph.py between human_confirm and
    generate_explanation, including the RAG retry loop."""
    for node in (lookup_reference_ranges_node, compute_trend_node, classify_severity_node):
        state.update(node(state))
    state.update(rag_retrieve_node(state))
    while route_after_rag(state) == "rag_retrieve_node" and state.get("rag_retry_count", 0) < MAX_RAG_RETRIES:
        state.update(rag_retrieve_node(state))
    return state


def build_fixtures(n: int = 6) -> list[dict]:
    """Picks up to n confirmed lab panels, stratified by (recomputed) severity
    so the set covers critical / worsening / stable rather than n near-copies
    of the most common case."""
    engine = get_engine()
    with Session(engine) as session:
        docs = session.execute(
            select(Document).where(Document.document_type == "lab_panel").order_by(Document.document_date)
        ).scalars().all()
        candidates = []
        for doc in docs:
            extraction = _extraction_from_db(session, doc)
            if len(extraction["values"]) >= MIN_VALUES:
                candidates.append((doc.id, extraction))

    by_severity: dict[str, list[dict]] = {}
    for doc_id, extraction in candidates:
        state = {"patient_id": PATIENT_ID, "extraction": extraction}
        state.update(classify_severity_node({**state, **lookup_reference_ranges_node(state)}))
        by_severity.setdefault(state["severity"], []).append({"doc_id": doc_id, "extraction": extraction})

    # Round-robin across severity classes, most recent documents first.
    picked = []
    pools = {k: list(reversed(v)) for k, v in sorted(by_severity.items())}
    while len(picked) < n and any(pools.values()):
        for pool in pools.values():
            if pool and len(picked) < n:
                picked.append(pool.pop(0))

    fixtures = []
    for item in picked:
        state = _run_upstream({"patient_id": PATIENT_ID, "extraction": item["extraction"]})
        fixtures.append({"fixture_id": item["doc_id"][:8], **state})
    return fixtures


def load_fixtures(n: int = 6, rebuild: bool = False) -> list[dict]:
    if FIXTURES_FILE.exists() and not rebuild:
        fixtures = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
        if len(fixtures) >= n:
            return fixtures[:n]
    fixtures = build_fixtures(n)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURES_FILE.write_text(json.dumps(fixtures, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return fixtures
