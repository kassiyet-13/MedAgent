"""
Creates data/medagent.db (gitignored) and seeds the reference_ranges table
from mcp_server/data/reference_ranges.json, plus a default patient row.

Run: python -m data.seed_db
Safe to re-run -- uses INSERT OR REPLACE semantics via merge.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
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


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        n = seed_reference_ranges(session)
        seed_default_patient(session)
        session.commit()

    print(f"Seeded {n} reference ranges into {DB_PATH}")
    print(f"Default patient id: {DEFAULT_PATIENT_ID}")


if __name__ == "__main__":
    main()
