"""
Semi-automated "new marker" onboarding, requested after real use surfaced two
unmatched markers (мочевина / UREA, билирубин непрямой / BILI_INDIRECT --
both were added by hand this session as a worked example). The user then
asked whether this has to be done manually every time.

Deliberately NOT fully automatic: an LLM silently inventing a clinical
"normal range" and writing it straight into the reference database is a
patient-safety risk (the same reasoning that made human_confirm_node
unconditional rather than confidence-gated, see graph/nodes.py -- a model
can be confidently wrong). Instead this drafts a candidate reference_ranges
entry for a human to review/edit/approve on the confirmation screen
(app/streamlit_app.py) before anything is written to reference_ranges.json.

Once approved and merged, everything downstream picks the new marker code up
automatically with no further code changes -- ocr/vision_extract.py reads
its known-marker list from reference_ranges.json at prompt-build time, and
app/pages/2_history_trends.py falls any uncategorized marker_code into a
catch-all "Басқа" group. Only the (optional, cosmetic) skills/glossary.py
blurb is NOT auto-added -- that stays a manual touch if a nicer explanation
card is wanted later.
"""
from __future__ import annotations

import json
from pathlib import Path

from llm_clients import get_traced_anthropic_client

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_RANGES_JSON = ROOT / "mcp_server" / "data" / "reference_ranges.json"
CLAUDE_MODEL = "claude-sonnet-5"

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "marker_code": {
            "type": "string",
            "description": "Short, unique, uppercase snake-ish code, e.g. 'UREA' or 'BILI_INDIRECT'. Must not collide with an existing code.",
        },
        "marker_name_en": {"type": "string"},
        "marker_name_ru": {"type": "string"},
        "marker_name_kz": {"type": "string"},
        "unit": {"type": "string", "description": "Prefer the unit actually printed on the report if given."},
        "normal_low": {"type": ["number", "null"]},
        "normal_high": {"type": ["number", "null"]},
        "critical_low": {"type": ["number", "null"]},
        "critical_high": {"type": ["number", "null"]},
        "cirrhosis_note": {
            "type": "string",
            "description": (
                "1-2 sentences: this marker's relevance to PBC/liver cirrhosis monitoring specifically. "
                "If it is NOT a liver-specific marker, say so plainly and note what it's usually tracked for instead -- "
                "do not overstate liver relevance."
            ),
        },
    },
    "required": [
        "marker_code",
        "marker_name_en",
        "marker_name_ru",
        "marker_name_kz",
        "unit",
        "cirrhosis_note",
    ],
}


def suggest_marker_entry(
    marker_name_as_written: str,
    unit: str | None,
    lab_ref_low: float | None,
    lab_ref_high: float | None,
    existing_codes: list[str],
) -> dict:
    """Drafts a candidate reference_ranges.json entry for a human to review.
    lab_ref_low/high (the range AS PRINTED on this specific report, already
    captured by ocr/vision_extract.py regardless of marker_code match) are
    passed as a strong prior -- real, patient-lab-calibrated numbers beat a
    generic textbook range when available."""
    prompt = f"""A Kazakhstani/Russian lab report contains a marker this app doesn't recognize
yet: "{marker_name_as_written}" (unit as read: {unit or 'unknown'}).
The report itself prints a reference range of {lab_ref_low}-{lab_ref_high} for it, if not null --
use that as a strong prior over a generic textbook range when present, since it's specific to
that lab's calibration.

Existing marker codes already in use (do NOT reuse one of these): {', '.join(existing_codes)}

Draft a new reference_ranges.json entry for this marker, for a patient-education app used by
a Primary Biliary Cholangitis / liver cirrhosis patient. Be honest in cirrhosis_note if this
marker isn't actually liver-specific."""

    client = get_traced_anthropic_client()
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        tools=[
            {
                "name": "suggest_reference_range",
                "description": "Record the drafted reference_ranges.json entry.",
                "input_schema": SUGGEST_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": "suggest_reference_range"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return dict(block.input)
    raise RuntimeError("Claude did not return a tool_use block")


def add_marker_entry(entry: dict) -> None:
    """Appends an approved entry to reference_ranges.json and reseeds the
    reference_ranges SQL table (data/seed_db.py::seed_reference_ranges uses
    session.merge -- idempotent upsert by marker_code, safe to rerun)."""
    # .get() with fallbacks throughout -- same lesson as the Streamlit form
    # (app/streamlit_app.py): a forced tool_choice call does not strictly
    # guarantee every "required" schema field comes back populated, and
    # marker_name_en specifically is never shown/edited in the approval UI
    # at all, so it must never be accessed with a bare [] here.
    marker_code = (entry.get("marker_code") or "").strip()
    if not marker_code:
        raise ValueError("marker_code is required to add a reference_ranges entry")

    data = json.loads(REFERENCE_RANGES_JSON.read_text(encoding="utf-8"))
    data["markers"] = [m for m in data["markers"] if m["marker_code"] != marker_code]
    data["markers"].append(
        {
            "marker_code": marker_code,
            "marker_name_en": entry.get("marker_name_en") or entry.get("marker_name_ru") or marker_code,
            "marker_name_ru": entry.get("marker_name_ru") or marker_code,
            "marker_name_kz": entry.get("marker_name_kz") or marker_code,
            "unit": entry.get("unit") or "",
            "normal_low": entry.get("normal_low"),
            "normal_high": entry.get("normal_high"),
            "critical_low": entry.get("critical_low"),
            "critical_high": entry.get("critical_high"),
            "cirrhosis_note": entry.get("cirrhosis_note") or "",
            "udca_response_role": None,
        }
    )
    REFERENCE_RANGES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    from data.seed_db import get_engine, seed_reference_ranges
    from sqlalchemy.orm import Session

    with Session(get_engine()) as session:
        seed_reference_ranges(session)
        session.commit()
