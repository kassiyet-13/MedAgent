"""
Tool 2: compute_trend

Plan Section 3: "trend math on medical values must be testable, not generated" --
this is deliberately plain SQL + arithmetic, never an LLM call. Includes the
MELD-Na calculation (standard OPTN 2016 formula), which is one of the app's
most safety-relevant numbers, so it lives here as a pure, unit-tested function.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Document, LabValueRow

# SI-unit to mg/dL conversion factors, since the MELD-Na formula is defined
# in US conventional units but this app stores everything in SI units
# (see mcp_server/data/reference_ranges.json _meta note).
UMOL_L_TO_MG_DL_BILIRUBIN = 17.1
UMOL_L_TO_MG_DL_CREATININE = 88.4


def compute_meld_na(
    bilirubin_umol_l: float | None,
    inr: float | None,
    creatinine_umol_l: float | None,
    sodium_mmol_l: float | None,
) -> float | None:
    """
    Standard OPTN 2016 MELD-Na formula. Returns None if any required input is
    missing -- callers must not guess/impute values for a safety-relevant score.
    """
    if bilirubin_umol_l is None or inr is None or creatinine_umol_l is None or sodium_mmol_l is None:
        return None

    bilirubin_mg_dl = max(bilirubin_umol_l / UMOL_L_TO_MG_DL_BILIRUBIN, 1.0)
    creatinine_mg_dl = max(creatinine_umol_l / UMOL_L_TO_MG_DL_CREATININE, 1.0)
    creatinine_mg_dl = min(creatinine_mg_dl, 4.0)  # OPTN cap (ignores dialysis-specific rule)
    inr_bounded = max(inr, 1.0)

    meld = (
        0.957 * math.log(creatinine_mg_dl)
        + 0.378 * math.log(bilirubin_mg_dl)
        + 1.120 * math.log(inr_bounded)
        + 0.643
    )
    meld = round(meld * 10)

    if meld <= 11:
        return float(meld)

    na_bounded = min(max(sodium_mmol_l, 125), 137)
    meld_na = meld + 1.32 * (137 - na_bounded) - (0.033 * meld * (137 - na_bounded))
    return round(meld_na)


def compute_trend(
    session: Session,
    patient_id: str,
    marker_codes: list[str],
    lookback_n_reports: int = 5,
) -> dict:
    """
    Returns:
    {
      "markers": {
        "<marker_code>": {
          "values": [{"date": ..., "value": ..., "unit": ...}, ...],  # oldest -> newest
          "direction": "improving"|"worsening"|"stable"|"insufficient_data",
          "pct_change_last_vs_previous": float | None,
        },
        ...
      },
      "meld_na_series": [{"date": ..., "meld_na": float}, ...]
    }
    "improving"/"worsening" is a naive default (assumes lower = better, which is
    true for ALT/AST/bilirubin/INR/etc. but NOT for albumin/platelets) --
    classify_severity_node (LangGraph) is responsible for marker-aware
    interpretation; this tool only reports the raw numeric direction.
    """
    rows = (
        session.execute(
            select(LabValueRow, Document.document_date)
            .join(Document, LabValueRow.document_id == Document.id)
            .where(Document.patient_id == patient_id)
            .where(LabValueRow.marker_code.in_(marker_codes))
            .order_by(Document.document_date.asc())
        )
        .all()
    )

    by_marker: dict[str, list[dict]] = {code: [] for code in marker_codes}
    for lab_value, doc_date in rows:
        if lab_value.value_numeric is None:
            continue
        # A value from a document with no parsed date can't be placed on a
        # trend timeline (and breaks sorting downstream) -- exclude at the
        # source rather than special-casing None dates in every consumer.
        if doc_date is None:
            continue
        by_marker[lab_value.marker_code].append(
            {"date": doc_date, "value": lab_value.value_numeric, "unit": lab_value.unit}
        )

    markers_out = {}
    for code, series in by_marker.items():
        series = series[-lookback_n_reports:]
        if len(series) < 2:
            direction = "insufficient_data"
            pct_change = None
        else:
            prev, last = series[-2]["value"], series[-1]["value"]
            pct_change = None if prev == 0 else round((last - prev) / abs(prev) * 100, 1)
            if last == prev:
                direction = "stable"
            else:
                direction = "worsening" if last > prev else "improving"
        markers_out[code] = {"values": series, "direction": direction, "pct_change_last_vs_previous": pct_change}

    meld_inputs_by_date: dict[str, dict] = {}
    for code in ("BILI_TOTAL", "INR", "CREATININE", "SODIUM"):
        for point in by_marker.get(code, []):
            meld_inputs_by_date.setdefault(point["date"], {})[code] = point["value"]

    meld_series = []
    for date in sorted(meld_inputs_by_date):
        vals = meld_inputs_by_date[date]
        score = compute_meld_na(
            bilirubin_umol_l=vals.get("BILI_TOTAL"),
            inr=vals.get("INR"),
            creatinine_umol_l=vals.get("CREATININE"),
            sodium_mmol_l=vals.get("SODIUM"),
        )
        if score is not None:
            meld_series.append({"date": date, "meld_na": score})

    return {"markers": markers_out, "meld_na_series": meld_series}
