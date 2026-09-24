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
