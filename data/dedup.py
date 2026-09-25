"""
Content-hash-based upload deduplication.

User question: "мен бір анализді қайта қайта жүктесем система оны жаңадан
сақтай ма жоқ сол бұрынғы анализді жаңарта ма?" (if I upload the same
analysis repeatedly, does it save a new one or update the old one?). Answer
was "always a new record" -- ingest_node generated a fresh random
document_id on every single upload with no duplicate check at all, confirmed
as a real problem by this session's own repeated test uploads (e.g.
узи.jpeg ended up saved 5 separate times).

SHA-256 of the raw file bytes was chosen over a date-based check: it's free
(no OCR/LLM call needed, checked before spending one), and it only flags an
EXACT re-upload -- the actual observed problem -- rather than risking a false
positive on two genuinely different documents that happen to share a
document_date (rare but real: e.g. a lab panel and a discharge summary from
the same hospital visit).
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Document


def compute_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_existing_document(session: Session, patient_id: str, content_hash: str) -> Document | None:
    return session.execute(
        select(Document).where(Document.patient_id == patient_id, Document.content_hash == content_hash)
    ).scalars().first()


# --- Content-level (same analysis, different file) ---
# Real-usage bug report: in the multi-lab upload, "Келесі анализ" seemed to
# reopen the analysis just saved. It was a different file with the same
# analysis inside -- the lab had sent the results twice (MR_20250805_*.PDF and
# MR_20250901_*.PDF), so the bytes and the hash differ and the check above
# can't see it; one analysis ended up saved twice, doubling its trend points.
# Compared after OCR, on what the document says: same registration date/time
# plus mostly the same values. Overlap rather than exact equality, because the
# saved copy may carry the user's corrections from the confirm step.

SAME_CONTENT_MIN_OVERLAP = 0.8


def _value_key(v) -> tuple:
    get = v.get if isinstance(v, dict) else lambda k: getattr(v, k, None)
    value = get("value") if isinstance(v, dict) else get("value_numeric")
    marker = get("marker_code") or (get("marker_name_as_written") or "").strip().lower()
    shown = round(value, 4) if value is not None else (get("value_text") or "").strip().lower()
    return (marker, shown)


def same_content(date_a: str | None, values_a, date_b: str | None, values_b) -> bool:
    if not date_a or not date_b or date_a[:16] != date_b[:16]:
        return False
    a, b = {_value_key(v) for v in values_a}, {_value_key(v) for v in values_b}
    if not a or not b:
        return False
    return len(a & b) / max(len(a), len(b)) >= SAME_CONTENT_MIN_OVERLAP


def find_same_content_lab_document(session: Session, patient_id: str, extraction: dict) -> Document | None:
    """A saved lab panel with the same registration date/time and mostly the
    same values as this extraction, or None."""
    from data.models import LabValueRow

    date = extraction.get("document_date")
    if not date:
        return None
    candidates = session.execute(
        select(Document).where(
            Document.patient_id == patient_id,
            Document.document_type == "lab_panel",
            Document.document_date.like(f"{date[:16]}%"),
        )
    ).scalars().all()
    for doc in candidates:
        rows = session.execute(select(LabValueRow).where(LabValueRow.document_id == doc.id)).scalars().all()
        if same_content(date, extraction.get("values", []), doc.document_date, rows):
            return doc
    return None
