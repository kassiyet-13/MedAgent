"""
Graph state schema. Plan Section 2 -- everything downstream (validation,
HITL, severity classification, explanation) reads/writes this one shared
dict as the graph executes.
"""
from __future__ import annotations

from typing import Literal, TypedDict


class MedAgentState(TypedDict, total=False):
    # --- input ---
    patient_id: str
    thread_id: str
    raw_file_path: str
    file_type: Literal["image", "pdf"]
    content_hash: str  # SHA-256 of the raw file bytes, computed in ingest_node -- data/dedup.py

    # --- classification / routing ---
    document_type: Literal["lab_panel", "narrative"]

    # --- structured (lab_panel) path ---
    extraction: dict  # serialized LabExtraction
    extraction_confidence: float
    confirm_attempts: int
    user_confirmed_extraction: bool
    reference_ranges: dict
    trend: dict
    severity: Literal["improving", "stable", "worsening", "critical"]
    escalation_level: Literal["routine", "see_doctor_soon", "seek_care_now"]

    # --- narrative path ---
    narrative_text: str
    document_kind: str | None
    document_date: str | None

    # --- RAG / explanation (shared) ---
    rag_context: list[dict]
    rag_retry_count: int
    explanation_ru: str
    explanation_kz: str
    disclaimer_present: bool

    # --- persistence ---
    user_confirmed_save: bool
    document_id: str
    assessment_id: str

    # --- internal scratch fields ---
    # NOTE: LangGraph only persists/merges keys declared in this TypedDict --
    # a node returning a key NOT listed here is silently dropped (no channel
    # exists for it). Caught during Day 3 testing: these were originally
    # undeclared and _inconsistent_rows/_tone/etc. were vanishing between
    # node calls without any error. Every key any node returns must be
    # declared here, underscore prefix or not.
    _inconsistent_rows: list[str]
    _critical_marker: str | None
    _critical_reason: str | None
    _tone: str
    _patient_history_chunks_added: int
    _injection_detected: bool
    _injection_patterns: list[str]
