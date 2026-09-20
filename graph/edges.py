"""
Conditional edge functions. Plan Section 2, updated per the Day-2 finding:
human_confirm_node is now unconditional (always reached after validation),
not gated by confidence -- see route_after_validate below.
"""
from __future__ import annotations

MAX_CONFIRM_ATTEMPTS = 3
MAX_RAG_RETRIES = 2


def route_after_classify(state: dict) -> str:
    return "validate_extraction_node" if state["document_type"] == "lab_panel" else "pii_scrub_node"


def route_after_validate(state: dict) -> str:
    """Always goes to human_confirm_node (unconditional -- Day 2 finding:
    a 0.95-confidence extraction was still badly wrong on a dense real
    document, so confidence can no longer gate this step). The only escape
    hatch is the confirm-attempt loop limit."""
    if state.get("confirm_attempts", 0) > MAX_CONFIRM_ATTEMPTS:
        return "escalate_unreadable"
    return "human_confirm_node"


def route_after_human_confirm(state: dict) -> str:
    if state.get("user_confirmed_extraction"):
        return "lookup_reference_ranges_node"
    if state.get("confirm_attempts", 0) > MAX_CONFIRM_ATTEMPTS:
        return "escalate_unreadable"
    return "validate_extraction_node"


def route_after_severity(state: dict) -> str:
    severity = state.get("severity")
    if severity == "critical":
        return "escalate_node"
    if severity == "worsening":
        return "decline_recommendation_node"
    return "encouragement_node"


def route_after_rag(state: dict) -> str:
    results = state.get("rag_context", [])
    low_relevance = (not results) or all((r.get("similarity_score") or 0) < 0.3 for r in results)
    if low_relevance and state.get("rag_retry_count", 0) < MAX_RAG_RETRIES:
        return "rag_retrieve_node"
    return "generate_explanation_node"
