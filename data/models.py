"""
SQLAlchemy ORM models -- the data model from plan Section 6.

One SQLite file (data/medagent.db, gitignored) backs the whole app.
`documents` generalizes the old "lab_reports" concept to cover both
document kinds (lab_panel / narrative) per the dual-RAG architecture.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(default="Patient")
    dob: Mapped[str | None] = mapped_column(default=None)
    sex: Mapped[str | None] = mapped_column(default=None)
    condition: Mapped[str] = mapped_column(default="pbc_cirrhosis")
    on_udca: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    documents: Mapped[list["Document"]] = relationship(back_populates="patient")


class Document(Base):
    """One uploaded file -- either a lab_panel or a narrative document."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    document_type: Mapped[str] = mapped_column()  # "lab_panel" | "narrative"
    document_kind: Mapped[str | None] = mapped_column(default=None)  # e.g. discharge_summary, fibroscan_report
    document_date: Mapped[str | None] = mapped_column(default=None)  # ISO date, as extracted
    uploaded_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    source_filename: Mapped[str | None] = mapped_column(default=None)
    raw_file_path: Mapped[str | None] = mapped_column(default=None)
    ocr_confidence: Mapped[float | None] = mapped_column(default=None)
    extraction_status: Mapped[str] = mapped_column(default="pending")  # pending|confirmed|escalated
    content_hash: Mapped[str | None] = mapped_column(default=None, index=True)  # SHA-256 of raw file bytes, for upload dedup (data/dedup.py)

    patient: Mapped["Patient"] = relationship(back_populates="documents")
    lab_values: Mapped[list["LabValueRow"]] = relationship(back_populates="document")
    assessment: Mapped["Assessment"] = relationship(back_populates="document", uselist=False)


class ReferenceRange(Base):
    """Seed table, loaded once from mcp_server/data/reference_ranges.json."""

    __tablename__ = "reference_ranges"

    marker_code: Mapped[str] = mapped_column(primary_key=True)
    marker_name_en: Mapped[str] = mapped_column()
    marker_name_ru: Mapped[str] = mapped_column()
    marker_name_kz: Mapped[str] = mapped_column()
    unit: Mapped[str] = mapped_column()
    normal_low: Mapped[float | None] = mapped_column(default=None)
    normal_high: Mapped[float | None] = mapped_column(default=None)
    critical_low: Mapped[float | None] = mapped_column(default=None)
    critical_high: Mapped[float | None] = mapped_column(default=None)
    cirrhosis_note: Mapped[str | None] = mapped_column(default=None)
    udca_response_role: Mapped[str | None] = mapped_column(default=None)
    is_qualitative: Mapped[bool] = mapped_column(default=False)


class LabValueRow(Base):
    __tablename__ = "lab_values"

    id: Mapped[str] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    marker_code: Mapped[str | None] = mapped_column(default=None)
    marker_name_as_written: Mapped[str] = mapped_column()
    value_numeric: Mapped[float | None] = mapped_column(default=None)
    value_text: Mapped[str | None] = mapped_column(default=None)  # qualitative result as written, e.g. "отсутствуют", "1:80" -- see ocr/schema.py::LabValue.value_text
    unit: Mapped[str | None] = mapped_column(default=None)
    lab_reported_ref_low: Mapped[float | None] = mapped_column(default=None)
    lab_reported_ref_high: Mapped[float | None] = mapped_column(default=None)
    lab_flag: Mapped[str | None] = mapped_column(default=None)
    extracted_confidence: Mapped[float | None] = mapped_column(default=None)
    user_confirmed: Mapped[bool] = mapped_column(default=False)

    document: Mapped["Document"] = relationship(back_populates="lab_values")


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    meld_na_score: Mapped[float | None] = mapped_column(default=None)
    child_pugh_estimate: Mapped[str | None] = mapped_column(default=None)
    udca_response_status: Mapped[str | None] = mapped_column(default=None)  # per Paris-II, if applicable
    overall_status: Mapped[str | None] = mapped_column(default=None)  # improving|stable|worsening|critical
    escalation_level: Mapped[str | None] = mapped_column(default=None)  # routine|see_doctor_soon|seek_care_now
    explanation_ru: Mapped[str | None] = mapped_column(default=None)
    explanation_kz: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    document: Mapped["Document"] = relationship(back_populates="assessment")


class EscalationLogEntry(Base):
    """Deterministic safety audit trail -- every escalation decision, logged regardless of LLM output."""

    __tablename__ = "escalation_log"

    id: Mapped[str] = mapped_column(primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"))
    marker_code: Mapped[str | None] = mapped_column(default=None)
    trigger_reason: Mapped[str] = mapped_column()
    escalation_level: Mapped[str] = mapped_column()
    timestamp: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Checkin(Base):
    """Weekly symptom/mood self-report (extra feature 3, plan Section 11)."""

    __tablename__ = "checkins"

    id: Mapped[str] = mapped_column(primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    fatigue_level: Mapped[int | None] = mapped_column(default=None)  # 1-5
    swelling: Mapped[bool | None] = mapped_column(default=None)
    appetite_level: Mapped[int | None] = mapped_column(default=None)  # 1-5
    confusion_level: Mapped[int | None] = mapped_column(default=None)  # 0-4, West-Haven-inspired
    notes: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Feedback(Base):
    """Real-user feedback capture -- business-value bonus (plan grading criteria)."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    assessment_id: Mapped[str | None] = mapped_column(default=None)
    rating: Mapped[int | None] = mapped_column(default=None)
    comment: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
