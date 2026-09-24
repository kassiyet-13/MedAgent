"""
History/trends page -- redesigned per real-usage feedback:
1. Trend/chart section now comes FIRST (was buried below the document list;
   feedback: "Негізгі бөлім ол динамика... оны бірінші орынға шығарған дұрыс").
2. Key liver markers (ALT, AST, GGT, ALP, bilirubin, albumin) shown as a
   default multi-line overview chart, rather than a flat alphabetical
   dropdown of all 24 markers mixed together (feedback: "түк түсініксіз").
3. Remaining markers grouped by panel (Biochemistry / Coagulation / CBC /
   Other) with a per-panel selector, matching how KZ lab printouts
   themselves group markers (feedback: "бірінші Биохимия кетеді, одан кейін
   ОАК").
4. Document list moved below, grouped by year/month, capped at the most
   recent 10, sorted by the document's OWN date (document_date) rather than
   upload timestamp (feedback: both the ordering complaint and the
   "2020-10-30 vs 12.12.2024" date-bug report -- the date bug itself was an
   OCR extraction fix in ocr/vision_extract.py; this page just needed to
   consistently sort/group by that corrected field).
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text
from sqlalchemy.orm import Session

from data.models import Document, ReferenceRange
from data.seed_db import get_engine
from mcp_server.tools.trend import compute_trend

PATIENT_ID = "patient_default"

st.set_page_config(page_title="MedAgent -- Тарих", page_icon="📈")
st.title("📈 Тарих және динамика")

engine = get_engine()

KEY_LIVER_MARKERS = ["ALT", "AST", "GGT", "ALP", "BILI_TOTAL", "ALBUMIN"]

PANELS = {
    "Биохимия (негізгі бауыр маркерлері)": ["ALT", "AST", "GGT", "ALP", "BILI_TOTAL", "BILI_DIRECT", "BILI_INDIRECT", "ALBUMIN", "TOTAL_PROTEIN"],
    "Коагулограмма (қан ұю)": ["INR", "PT_SEC", "PTI", "APTT", "FIBRINOGEN", "TT_SEC"],
    "ОАК (негізгі)": ["WBC", "RBC", "HGB", "HCT", "PLATELETS", "ESR", "ESR_ANALYZER"],
    # ОАК's leukocyte differential and erythrocyte indices got added via the
    # "suggest & approve new marker" flow (ocr/marker_suggest.py) after a
    # detailed CBC upload -- split into their own sub-panels rather than
    # letting them all fall into the catch-all "Басқа" bucket (too many
    # unrelated series crammed into one chart was part of the "colors don't
    # match the legend" complaint: too many lines for a readable palette).
    "ОАК (лейкоцит формуласы)": ["NEU_PCT", "NEU_ABS", "LYM_PCT", "LYM_ABS", "MON_PCT", "MON_ABS", "EOS_PCT", "EOS_ABS", "BAS_PCT", "BAS_ABS"],
    "ОАК (эритроцит индекстері)": ["MCV", "MCH", "MCHC", "RDW_SD", "MPV"],
    "Басқа": ["CREATININE", "UREA", "SODIUM", "AFP", "AMA_M2", "IGM"],
}

# Any marker_code that exists in reference_ranges.json but isn't in one of
# the curated groups above (e.g. one added later via the "suggest & approve
# new marker" flow on the confirmation screen, app/streamlit_app.py) still
# needs somewhere to show up -- falls into "Басқа" automatically rather than
# silently having no trend chart until someone remembers to edit this file.
_categorized = {code for markers in PANELS.values() for code in markers}
with Session(engine) as _s:
    _all_known_codes = [r[0] for r in _s.execute(text("SELECT marker_code FROM reference_ranges")).all()]
for _code in _all_known_codes:
    if _code not in _categorized:
        PANELS["Басқа"].append(_code)

ALL_MARKERS = [code for markers in PANELS.values() for code in markers]

# Short Russian labels for chart legends specifically (an intentional,
# scoped override of the app's KZ-first convention for THIS use only, per
# explicit feedback: "қысқартылған орысша аттарын шығар, мысалы АЛТ, АСТ").
# reference_ranges.json's marker_name_ru is the full clinical name, e.g.
# "Аланинаминотрансфераза (АЛТ)" -- correct for the glossary/explanation
# text, but too long for a chart legend: real bug found via this feedback --
# long names made the legend row truncate ("...") and HIDE entries for
# series that were still drawn on the chart, which is what actually looked
# like "chart colors don't match the legend" (the line was there, its
# legend swatch just wasn't visible). A hand-curated short-form dict is used
# instead of trying to algorithmically parse the long name (parenthesized
# text isn't reliably an abbreviation -- e.g. "Эозинофилы (абсолютное
# число)" would wrongly yield "абсолютное число"). New markers added later
# via the marker-suggest flow (ocr/marker_suggest.py) that aren't in this
# dict fall back to the full marker_name_ru -- may need a short label added
# here by hand if it turns out too long in practice.
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

with Session(engine) as session:
    trend = compute_trend(session, PATIENT_ID, ALL_MARKERS, lookback_n_reports=20)
    MARKER_NAMES_RU = {r.marker_code: r.marker_name_ru for r in session.query(ReferenceRange).all()}


def _label(code: str) -> str:
    return SHORT_LABEL_RU.get(code) or MARKER_NAMES_RU.get(code, code)


def _multi_line_chart(combined: pd.DataFrame) -> None:
    """Renders a wide date-indexed DataFrame (one column per marker) as a
    multi-line chart with a legend that WRAPS instead of truncating.

    Real bug found via feedback ("түстер сәйкес емес" -- chart colors don't
    match the legend): st.line_chart's built-in legend is a single row that,
    past ~5-6 series, hides entries entirely rather than wrapping (confirmed
    via the accessibility tree: an 8-series chart's legend only exposed 5
    swatches in the DOM even after shortening labels) -- a line was drawn
    with no visible matching legend entry, which is what actually looked
    like a color mismatch. Altair's legend supports wrapping (`columns=`),
    and since the chart marks and the legend swatches share one encoding,
    correct color correspondence is structurally guaranteed rather than
    hoped for."""
    long_df = combined.reset_index().melt(id_vars="date", var_name="Көрсеткіш", value_name="value").dropna(subset=["value"])
    chart = (
        alt.Chart(long_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:N", title=None),
            y=alt.Y("value:Q", title=None),
            color=alt.Color("Көрсеткіш:N", legend=alt.Legend(orient="bottom", columns=3, title=None)),
        )
    )
    st.altair_chart(chart, use_container_width=True)

markers_with_data = {code: info for code, info in trend["markers"].items() if info["values"]}

if not markers_with_data:
    st.info("Әзірге жүктелген құжат жоқ. Басты бетте бір анализ немесе құжат жүктеңіз.")
    st.stop()

# --- Section 1: key liver markers overview (default view) ---
st.subheader("Негізгі бауыр көрсеткіштері")
key_present = [c for c in KEY_LIVER_MARKERS if c in markers_with_data]
if key_present:
    frames = []
    for code in key_present:
        df = pd.DataFrame(markers_with_data[code]["values"])
        if not df.empty:
            df = df.rename(columns={"value": _label(code)}).set_index("date")[[_label(code)]]
            frames.append(df)
    if frames:
        combined = frames[0]
        for f in frames[1:]:
            combined = combined.join(f, how="outer")
        _multi_line_chart(combined)
else:
    st.caption("Негізгі бауыр маркерлері (АЛТ, АСТ, ГГТ, ЩФ...) әлі жоқ.")

# --- Section 2: per-panel combined chart -- feedback: a single-marker
# selector only showed one line at a time (e.g. picking "ОАК" then still
# only seeing PLATELETS); the user wants every marker in the chosen group
# plotted together, same pattern as Section 1's key-liver-markers chart. ---
st.subheader("Топ бойынша көрсеткіштер")
panel_choice = st.selectbox("Топты таңдаңыз", list(PANELS.keys()))
panel_markers_present = [c for c in PANELS[panel_choice] if c in markers_with_data]

if not panel_markers_present:
    st.caption("Бұл топта әлі деректер жоқ.")
else:
    frames = []
    for code in panel_markers_present:
        df = pd.DataFrame(markers_with_data[code]["values"])
        if not df.empty:
            df = df.rename(columns={"value": _label(code)}).set_index("date")[[_label(code)]]
            frames.append(df)
    if frames:
        combined = frames[0]
        for f in frames[1:]:
            combined = combined.join(f, how="outer")
        _multi_line_chart(combined)

    # Declutter -- feedback: repeating "деректер жеткіліксіз" for every
    # single-reading marker separately was noisy/confusing ("түсініксіз").
    # Only markers with an actual direction (>=2 readings) get their own
    # line; the rest are named once, together, in one short caption.
    direction_label = {
        "improving": "🟢 жақсарып келеді",
        "worsening": "🟡 нашарлап келеді",
        "stable": "⚪ тұрақты",
    }
    insufficient = []
    for code in panel_markers_present:
        info = markers_with_data[code]
        if info["direction"] in direction_label:
            st.caption(f"{_label(code)}: {direction_label[info['direction']]}")
        else:
            insufficient.append(_label(code))
    if insufficient:
        st.caption(f"Жеткіліксіз деректер (кемінде 2 өлшем қажет): {', '.join(insufficient)}")

if trend["meld_na_series"]:
    st.subheader("MELD-Na индексі")
    meld_df = pd.DataFrame(trend["meld_na_series"])
    st.line_chart(meld_df.set_index("date")["meld_na"])
    st.caption(
        "MELD-Na — бауыр ауруының ауырлығын бағалайтын халықаралық индекс. "
        "Бұл диагноз емес, тек динамиканы бақылауға арналған сан."
    )

# --- Section 3: document list, grouped by year/month, last 10 ---
st.subheader("Жүктелген құжаттар (соңғы 10)")

with Session(engine) as session:
    docs = (
        session.query(Document)
        .filter(Document.patient_id == PATIENT_ID)
        .order_by(Document.document_date.desc().nulls_last())
        .limit(10)
        .all()
    )

if not docs:
    st.caption("Құжат жоқ.")
else:
    by_year_month: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        key = (d.document_date or "Күні белгісіз")[:7] if d.document_date else "Күні белгісіз"
        by_year_month[key].append(d)

    for ym in sorted(by_year_month.keys(), reverse=True):
        st.markdown(f"**{ym}**")
        rows = [
            {"Күні": d.document_date or "—", "Түрі": d.document_type, "Жіктелімі": d.document_kind or "", "Файл": d.source_filename}
            for d in by_year_month[ym]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
