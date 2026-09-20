"""
Assembles the LangGraph state machine. Plan Section 16: "the riskiest
integration point in the whole project" -- the checkpointer here is what
makes interrupt()/Command(resume=...) survive across separate process
invocations (and, once wired into Streamlit on Day 4, across Streamlit's
rerun-per-interaction model).
"""
from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from graph.edges import route_after_classify, route_after_human_confirm, route_after_rag, route_after_severity, route_after_validate
from graph.nodes import (
    classify_document_type_node,
    compute_trend_node,
    decline_recommendation_node,
    disclaimer_check_node,
    encouragement_node,
    escalate_node,
    escalate_unreadable_node,
    generate_explanation_node,
    human_confirm_node,
    ingest_node,
    ingest_patient_history_node,
    lookup_reference_ranges_node,
    ocr_extract_lab_node,
    ocr_extract_narrative_node,
    persist_node,
    pii_scrub_node,
    rag_retrieve_node,
    save_confirm_node,
    classify_severity_node,
    validate_extraction_node,
)
from graph.state import MedAgentState

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_DB = ROOT / "data" / "langgraph_checkpoints.db"


def build_graph(checkpointer=None):
    g = StateGraph(MedAgentState)

    g.add_node("ingest_node", ingest_node)
    g.add_node("classify_document_type_node", classify_document_type_node)

    # lab_panel path
    g.add_node("ocr_extract_lab_node", ocr_extract_lab_node)
    g.add_node("validate_extraction_node", validate_extraction_node)
    g.add_node("human_confirm_node", human_confirm_node)
    g.add_node("escalate_unreadable_node", escalate_unreadable_node)
    g.add_node("lookup_reference_ranges_node", lookup_reference_ranges_node)
    g.add_node("compute_trend_node", compute_trend_node)
    g.add_node("classify_severity_node", classify_severity_node)
    g.add_node("escalate_node", escalate_node)
    g.add_node("decline_recommendation_node", decline_recommendation_node)
    g.add_node("encouragement_node", encouragement_node)
    g.add_node("rag_retrieve_node", rag_retrieve_node)
    g.add_node("generate_explanation_node", generate_explanation_node)
    g.add_node("disclaimer_check_node", disclaimer_check_node)
    g.add_node("save_confirm_node", save_confirm_node)
    g.add_node("persist_node", persist_node)

    # narrative path
    g.add_node("ocr_extract_narrative_node", ocr_extract_narrative_node)
    g.add_node("pii_scrub_node", pii_scrub_node)
    g.add_node("ingest_patient_history_node", ingest_patient_history_node)

    g.set_entry_point("ingest_node")
    g.add_edge("ingest_node", "classify_document_type_node")

    g.add_conditional_edges(
        "classify_document_type_node",
        lambda s: "lab_panel" if s["document_type"] == "lab_panel" else "narrative",
        {"lab_panel": "ocr_extract_lab_node", "narrative": "ocr_extract_narrative_node"},
    )

    g.add_edge("ocr_extract_lab_node", "validate_extraction_node")
    g.add_conditional_edges(
        "validate_extraction_node",
        route_after_validate,
        {"human_confirm_node": "human_confirm_node", "escalate_unreadable": "escalate_unreadable_node"},
    )
    g.add_conditional_edges(
        "human_confirm_node",
        route_after_human_confirm,
        {
            "lookup_reference_ranges_node": "lookup_reference_ranges_node",
            "validate_extraction_node": "validate_extraction_node",
            "escalate_unreadable": "escalate_unreadable_node",
        },
    )
    g.add_edge("escalate_unreadable_node", END)

    g.add_edge("lookup_reference_ranges_node", "compute_trend_node")
    g.add_edge("compute_trend_node", "classify_severity_node")
    g.add_conditional_edges(
        "classify_severity_node",
        route_after_severity,
        {
            "escalate_node": "escalate_node",
            "decline_recommendation_node": "decline_recommendation_node",
            "encouragement_node": "encouragement_node",
        },
    )
    g.add_edge("escalate_node", "rag_retrieve_node")
    g.add_edge("decline_recommendation_node", "rag_retrieve_node")
    g.add_edge("encouragement_node", "rag_retrieve_node")

    g.add_conditional_edges(
        "rag_retrieve_node",
        route_after_rag,
        {"rag_retrieve_node": "rag_retrieve_node", "generate_explanation_node": "generate_explanation_node"},
    )
    g.add_edge("generate_explanation_node", "disclaimer_check_node")
    g.add_edge("disclaimer_check_node", "save_confirm_node")
    g.add_edge("save_confirm_node", "persist_node")
    g.add_edge("persist_node", END)

    g.add_edge("ocr_extract_narrative_node", "pii_scrub_node")
    g.add_edge("pii_scrub_node", "ingest_patient_history_node")
    g.add_edge("ingest_patient_history_node", END)

    return g.compile(checkpointer=checkpointer)


def get_sqlite_checkpointer_cm():
    """Returns the SqliteSaver context manager (caller must `with` it)."""
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver.from_conn_string(str(CHECKPOINT_DB))
