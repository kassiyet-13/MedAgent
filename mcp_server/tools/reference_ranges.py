"""
Tool 1: get_reference_ranges

Plan Section 3. Returns per-marker normal/critical ranges with PBC/cirrhosis-
adjusted notes for a given list of markers. Reads directly from the seeded
SQLite reference_ranges table (single source of truth, shared with the app).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import ReferenceRange


def get_reference_ranges(session: Session, markers: list[str], patient_context: dict | None = None) -> list[dict]:
    """
    markers: list of marker_code strings, e.g. ["ALT", "PLATELETS", "AMA_M2"].
    patient_context: {"condition": "pbc_cirrhosis", "age": int|None, "sex": str|None, "on_udca": bool}
        -- currently only used to decide whether to surface udca_response_role notes;
        reserved for future age/sex-specific range adjustment.
    Returns a list of dicts, one per requested marker found (unknown codes are skipped,
    not errored -- the caller/graph decides how to handle a miss).
    """
    patient_context = patient_context or {}
    on_udca = patient_context.get("on_udca", True)

    rows = session.execute(
        select(ReferenceRange).where(ReferenceRange.marker_code.in_(markers))
    ).scalars().all()

    results = []
    for row in rows:
        entry = {
            "marker_code": row.marker_code,
            "marker_name_en": row.marker_name_en,
            "marker_name_ru": row.marker_name_ru,
            "marker_name_kz": row.marker_name_kz,
            "unit": row.unit,
            "normal_low": row.normal_low,
            "normal_high": row.normal_high,
            "critical_low": row.critical_low,
            "critical_high": row.critical_high,
            "is_qualitative": row.is_qualitative,
            "cirrhosis_note": row.cirrhosis_note,
        }
        if on_udca and row.udca_response_role:
            entry["udca_response_role"] = row.udca_response_role
        results.append(entry)

    found_codes = {r.marker_code for r in rows}
    missing = [m for m in markers if m not in found_codes]
    if missing:
        for m in missing:
            results.append({"marker_code": m, "error": "unknown_marker_code"})

    return results
