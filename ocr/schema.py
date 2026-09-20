"""
Structured-output contracts for the OCR/extraction path.

LabExtraction is the schema enforced on the vision-LLM call in
vision_extract.py for lab-panel documents. Everything downstream
(validate_extraction_node, human_confirm_node, lookup_reference_ranges_node)
depends on this exact shape -- see plan Section 7 and Section 16 (critical files).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocumentType = Literal["lab_panel", "narrative"]


class LabValue(BaseModel):
    """One extracted marker reading from a lab panel image."""

    marker_name_as_written: str = Field(
        description="The marker name exactly as printed on the report (Russian/Kazakh/English)."
    )
    marker_code: str | None = Field(
        default=None,
        description=(
            "Best-guess match to a marker_code in mcp_server/data/reference_ranges.json "
            "(e.g. 'ALT', 'PT_SEC'). Null if no confident match -- validate_extraction_node "
            "will route this to human_confirm_node rather than silently guessing."
        ),
    )
    value: float | None = Field(default=None, description="Numeric value; null if unreadable.")
    unit: str | None = None
    lab_ref_low: float | None = Field(
        default=None, description="Lower bound of the reference range as printed on THIS report (may differ from our defaults)."
    )
    lab_ref_high: float | None = None
    lab_flag: str | None = Field(
        default=None, description="Any flag printed on the report itself, e.g. '!' or 'H'/'L'."
    )
    notes: str | None = Field(
        default=None, description="Free-text note on uncertainty, blur, or ambiguity for this specific value."
    )


class LabExtraction(BaseModel):
    """Full structured result of OCR-ing one lab panel document."""

    document_date: str | None = Field(default=None, description="ISO date (YYYY-MM-DD) if determinable from the report.")
    lab_name: str | None = Field(default=None, description="Issuing lab/clinic name, if present (kept for record-keeping, scrubbed before embedding).")
    values: list[LabValue] = Field(default_factory=list)
    overall_confidence: float = Field(
        ge=0.0, le=1.0, description="Model's self-assessed confidence in the extraction as a whole (0-1)."
    )
    possible_injection_detected: bool = Field(
        default=False,
        description="True if the document contains text that reads like an instruction to the AI rather than clinical content (prompt-injection guardrail signal).",
    )


class NarrativeExtraction(BaseModel):
    """Result of OCR-ing a narrative document (discharge summary, imaging report text)."""

    document_date: str | None = None
    document_kind: str | None = Field(
        default=None, description="Best guess, e.g. 'discharge_summary', 'ultrasound_report', 'fibroscan_report'."
    )
    text: str = Field(description="Transcribed clinically-relevant text, PII omitted per the extraction prompt.")
    possible_injection_detected: bool = False
