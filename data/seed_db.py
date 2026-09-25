"""
Creates data/medagent.db (gitignored) and seeds the reference_ranges table
from mcp_server/data/reference_ranges.json, plus a default patient row.

Run: python -m data.seed_db
Safe to re-run -- uses INSERT OR REPLACE semantics via merge.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from data.models import Base, Patient, ReferenceRange

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "medagent.db"
REFERENCE_RANGES_JSON = ROOT / "mcp_server" / "data" / "reference_ranges.json"
DEFAULT_PATIENT_ID = "patient_default"


def get_engine(db_path: Path = DB_PATH):
    return create_engine(f"sqlite:///{db_path}")


def seed_reference_ranges(session: Session) -> int:
    data = json.loads(REFERENCE_RANGES_JSON.read_text(encoding="utf-8"))
    count = 0
    for m in data["markers"]:
        row = ReferenceRange(
            marker_code=m["marker_code"],
            marker_name_en=m["marker_name_en"],
            marker_name_ru=m["marker_name_ru"],
            marker_name_kz=m["marker_name_kz"],
            unit=m["unit"],
            normal_low=m.get("normal_low"),
            normal_high=m.get("normal_high"),
            critical_low=m.get("critical_low"),
            critical_high=m.get("critical_high"),
            cirrhosis_note=m.get("cirrhosis_note"),
            udca_response_role=m.get("udca_response_role"),
            is_qualitative=m.get("is_qualitative", False),
        )
        session.merge(row)
        count += 1
    return count


def seed_default_patient(session: Session) -> None:
    existing = session.get(Patient, DEFAULT_PATIENT_ID)
    if existing is None:
        session.add(
            Patient(
                id=DEFAULT_PATIENT_ID,
                display_name="Patient",
                condition="pbc_cirrhosis",
                on_udca=True,
            )
        )


def ensure_content_hash_column(engine) -> None:
    """Base.metadata.create_all() only creates missing TABLES, not missing
    COLUMNS on a table that already exists -- the documents table already had
    rows in it when content_hash (upload-dedup, data/dedup.py) was added, so
    this lightweight migration adds the column if it isn't there yet. Safe to
    call every startup: checked via PRAGMA table_info first."""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(documents)")).fetchall()}
        if "content_hash" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN content_hash TEXT"))
            conn.commit()


def ensure_value_text_column(engine) -> None:
    """Same pattern as ensure_content_hash_column -- lab_values.value_text
    (qualitative lab results, e.g. "отсутствуют"/"1:80", see
    ocr/schema.py::LabValue.value_text) was added after the table already had
    rows."""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(lab_values)")).fetchall()}
        if "value_text" not in cols:
            conn.execute(text("ALTER TABLE lab_values ADD COLUMN value_text TEXT"))
            conn.commit()


def backfill_content_hashes(engine) -> int:
    """Documents created before content_hash existed have NULL for it -- the
    dedup check (data/dedup.py) can't catch a re-upload of one of those until
    it's backfilled. Real-usage finding: a user re-uploaded an already-saved
    analysis right after this feature shipped and got no warning, because the
    ONLY row for that file still had content_hash=NULL. Idempotent (only
    touches NULL rows) and safe to call every startup; reads each document's
    still-on-disk raw_file_path -- a document whose file was since deleted is
    left as NULL rather than erroring."""
    from pathlib import Path

    from data.dedup import compute_file_hash
    from data.models import Document

    updated = 0
    with Session(engine) as session:
        docs = session.query(Document).filter(Document.content_hash.is_(None)).all()
        for doc in docs:
            if doc.raw_file_path and Path(doc.raw_file_path).exists():
                doc.content_hash = compute_file_hash(Path(doc.raw_file_path).read_bytes())
                updated += 1
        session.commit()
    return updated


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(engine)
    ensure_content_hash_column(engine)
    ensure_value_text_column(engine)
    n_backfilled = backfill_content_hashes(engine)
    if n_backfilled:
        print(f"Backfilled content_hash for {n_backfilled} existing documents")

    with Session(engine) as session:
        n = seed_reference_ranges(session)
        seed_default_patient(session)
        session.commit()

    print(f"Seeded {n} reference ranges into {DB_PATH}")
    print(f"Default patient id: {DEFAULT_PATIENT_ID}")


if __name__ == "__main__":
    main()
