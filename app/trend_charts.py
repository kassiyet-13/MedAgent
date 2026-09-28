"""
Shared trend charts and per-marker status lines, used by the landing page
(pages/1_lab_upload.py) and the history page (pages/2_history_trends.py) so
every chart looks and reads the same.

Feedback round 2026-09-28: dates without the time, taller charts, a Kazakh
tooltip that shows the marker's normal range, a status line under every
chart. The status is judged against the NORMAL RANGE, not raw direction:
compute_trend's "improving"/"worsening" assumes lower = better (wrong for
albumin/platelets) and compares only the last two readings, so it labelled
ALT 84.7 (norm <= 41) "жақсарып келеді" because it dipped from 86.2.
"""
from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session

from data.models import ReferenceRange

# Short Russian labels for chart legends (feedback: "қысқартылған орысша
# аттарын шығар, мысалы АЛТ, АСТ"); long clinical names truncated the legend.
# Markers added later via the suggest-and-approve flow fall back to their
# full marker_name_ru.
SHORT_LABEL_RU = {
    "ALT": "АЛТ", "AST": "АСТ", "GGT": "ГГТ", "ALP": "ЩФ",
    "BILI_TOTAL": "Общий билирубин", "BILI_DIRECT": "Прямой билирубин", "BILI_INDIRECT": "Непрямой билирубин",
    "ALBUMIN": "Альбумин", "TOTAL_PROTEIN": "Общий белок",
    "INR": "МНО", "PT_SEC": "ПВ", "PTI": "ПТИ", "APTT": "АЧТВ", "FIBRINOGEN": "Фибриноген", "TT_SEC": "ТВ",
    "PLATELETS": "Тромбоциты", "WBC": "Лейкоциты", "RBC": "Эритроциты", "HGB": "Гемоглобин", "HCT": "Гематокрит",
    "ESR": "СОЭ", "ESR_ANALYZER": "СОЭ (анализатор)",
    "NEU_PCT": "Нейтрофилы %", "LYM_PCT": "Лимфоциты %", "MON_PCT": "Моноциты %", "EOS_PCT": "Эозинофилы %", "BAS_PCT": "Базофилы %",
    "NEU_ABS": "Нейтрофилы абс.", "LYM_ABS": "Лимфоциты абс.", "MON_ABS": "Моноциты абс.", "EOS_ABS": "Эозинофилы абс.", "BAS_ABS": "Базофилы абс.",
    "MCV": "MCV", "MCH": "MCH", "MCHC": "MCHC", "RDW_SD": "RDW-SD", "MPV": "MPV",
    "CREATININE": "Креатинин", "UREA": "Мочевина", "SODIUM": "Натрий",
    "AFP": "АФП", "AMA_M2": "АМА-M2", "IGM": "IgM",
}

# Biochemistry panel as grouped on KZ lab printouts -- shared by the landing
# chart and the history page's "Биохимия" group so they never drift apart.
BIOCHEMISTRY = ["ALT", "AST", "GGT", "ALP", "BILI_TOTAL", "BILI_DIRECT", "BILI_INDIRECT", "ALBUMIN", "TOTAL_PROTEIN"]

# "Негізгі бауыр көрсеткіштері" -- the same chart on the landing page and the
# history page (feedback: the full 9-marker biochemistry chart on the landing
# page had lines on top of each other; this 6-marker one reads clearly).
KEY_LIVER_MARKERS = ["ALT", "AST", "GGT", "ALP", "BILI_TOTAL", "ALBUMIN"]


def key_liver_section(trend_markers: dict, ranges: dict) -> bool:
    """Chart + status lines for the key liver markers. False if no data."""
    present = [c for c in KEY_LIVER_MARKERS if (trend_markers.get(c) or {}).get("values")]
    if not present:
        return False
    trend_chart(chart_rows(trend_markers, present, ranges))
    status_lines(trend_markers, present, ranges)
    return True

CHART_HEIGHT = 380
STABLE_TOLERANCE = 0.05  # <5% change in distance from the norm = "өзгеріссіз"


def load_ranges(session: Session) -> dict[str, dict]:
    return {
        r.marker_code: {"low": r.normal_low, "high": r.normal_high, "unit": r.unit, "name_ru": r.marker_name_ru}
        for r in session.query(ReferenceRange).all()
    }


def label(code: str, ranges: dict) -> str:
    return SHORT_LABEL_RU.get(code) or (ranges.get(code) or {}).get("name_ru") or code


def _day(iso: str) -> str:
    """'2026-07-22T10:35' -> '22.07.2026'."""
    try:
        return date.fromisoformat(iso[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return iso[:10]


def _distance_from_norm(value: float, low: float | None, high: float | None) -> float:
    """0 inside the normal range, else how far outside, relative to the
    boundary that was crossed (0.5 = 50% beyond it)."""
    if high is not None and value > high:
        return (value - high) / high if high else value
    if low is not None and value < low:
        return (low - value) / low if low else 0.0
    return 0.0


def _fmt(x: float) -> str:
    return f"{x:g}"


def point_status(value: float, low: float | None, high: float | None) -> str:
    """Tooltip text for one reading."""
    if low is None and high is None:
        return "норма белгісіз"
    if high is not None and value > high:
        return f"🔴 нормадан жоғары ({value / high:.1f} есе)" if high else "🔴 нормадан жоғары"
    if low is not None and value < low:
        return "🔴 нормадан төмен"
    return "🟢 қалыпты"


def marker_status(values: list[float], low: float | None, high: float | None) -> str:
    """Status of the LATEST reading vs its normal range, and whether it moved
    toward or away from the range since the previous reading. Works the same
    for "lower is better" (ALT) and "higher is better" (albumin) markers."""
    if low is None and high is None:
        return "⚪ норма белгісіз"
    last = values[-1]
    d_last = _distance_from_norm(last, low, high)
    if d_last == 0:
        if len(values) >= 2 and _distance_from_norm(values[-2], low, high) > 0:
            return "🟢 қалыпқа келді"
        return "🟢 қалыпты"
    if len(values) < 2:
        return "🔴 нормадан тыс"
    d_prev = _distance_from_norm(values[-2], low, high)
    if d_last < d_prev * (1 - STABLE_TOLERANCE):
        return "🟡 нормадан тыс, жақсарып келеді"
    if d_last > d_prev * (1 + STABLE_TOLERANCE):
        return "🔴 нормадан тыс, нашарлап келеді"
    return "🔴 нормадан тыс, өзгеріссіз"


def chart_rows(trend_markers: dict, codes: list[str], ranges: dict, last_n_dates: int | None = None) -> pd.DataFrame:
    rows = []
    for code in codes:
        r = ranges.get(code) or {}
        low, high, unit = r.get("low"), r.get("high"), r.get("unit") or ""
        norm = f"{_fmt(low) if low is not None else '…'}–{_fmt(high) if high is not None else '…'} {unit}".strip()
        for v in (trend_markers.get(code) or {}).get("values", []):
            if v.get("value") is None:
                continue
            rows.append({
                "date_iso": v["date"][:10],
                "Күні": _day(v["date"]),
                "Көрсеткіш": label(code, ranges),
                "value": v["value"],
                "Мәні": f"{_fmt(v['value'])} {v.get('unit') or unit}".strip(),
                "Норма": norm if (low is not None or high is not None) else "белгісіз",
                "Күйі": point_status(v["value"], low, high),
                "out_of_range": _distance_from_norm(v["value"], low, high) > 0,
            })
    df = pd.DataFrame(rows)
    if last_n_dates and not df.empty:
        keep = sorted(df["date_iso"].unique())[-last_n_dates:]
        df = df[df["date_iso"].isin(keep)]
    return df


def trend_chart(df: pd.DataFrame, height: int = CHART_HEIGHT) -> None:
    if df.empty:
        return
    x = alt.X("Күні:N", title=None, sort=alt.EncodingSortField(field="date_iso", op="min"), axis=alt.Axis(labelAngle=0))
    y = alt.Y("value:Q", title=None)
    color = alt.Color("Көрсеткіш:N", legend=alt.Legend(orient="bottom", columns=4, title=None))
    tooltip = ["Күні:N", "Көрсеткіш:N", "Мәні:N", "Норма:N", "Күйі:N"]
    lines = alt.Chart(df).mark_line().encode(x=x, y=y, color=color)
    # Out-of-range readings stand out without a legend lookup: bigger, with
    # a dark outline. A shaded normal band isn't drawn because every marker
    # on a shared axis has a different range.
    points = alt.Chart(df).mark_point(filled=True).encode(
        x=x, y=y, color=color, tooltip=tooltip,
        size=alt.condition("datum.out_of_range", alt.value(140), alt.value(45)),
        stroke=alt.condition("datum.out_of_range", alt.value("#14213D"), alt.value("transparent")),
        strokeWidth=alt.condition("datum.out_of_range", alt.value(1.5), alt.value(0)),
    )
    st.altair_chart((lines + points).properties(height=height), use_container_width=True)
    st.caption("Үлкен, қоршалған нүкте — нормадан тыс мән. Норманы көру үшін нүктеге тінтуірді апарыңыз.")


def meld_chart(series: list[dict], height: int = CHART_HEIGHT) -> None:
    df = pd.DataFrame(
        [{"date_iso": m["date"][:10], "Күні": _day(m["date"]), "MELD-Na": m["meld_na"]} for m in series]
    )
    if df.empty:
        return
    st.altair_chart(
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("Күні:N", title=None, sort=alt.EncodingSortField(field="date_iso", op="min"), axis=alt.Axis(labelAngle=0)),
            y=alt.Y("MELD-Na:Q", title=None),
            tooltip=["Күні:N", "MELD-Na:Q"],
        )
        .properties(height=height),
        use_container_width=True,
    )


def status_lines(trend_markers: dict, codes: list[str], ranges: dict) -> None:
    """One line per marker under a chart: latest value, its norm, status."""
    for code in codes:
        vals = [v["value"] for v in (trend_markers.get(code) or {}).get("values", []) if v.get("value") is not None]
        if not vals:
            continue
        r = ranges.get(code) or {}
        low, high, unit = r.get("low"), r.get("high"), r.get("unit") or ""
        norm = f" (норма {_fmt(low) if low is not None else '…'}–{_fmt(high) if high is not None else '…'})" if (low is not None or high is not None) else ""
        prev = f", алдыңғы: {_fmt(vals[-2])}" if len(vals) >= 2 else ""
        st.markdown(f"**{label(code, ranges)}**: {_fmt(vals[-1])} {unit}{norm} — {marker_status(vals, low, high)}{prev}")
