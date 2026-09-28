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


import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.trend_charts import BIOCHEMISTRY, chart_rows, key_liver_section, load_ranges, meld_chart, status_lines, trend_chart
from data.models import Document
from data.seed_db import get_engine
from mcp_server.tools.trend import compute_trend

PATIENT_ID = "patient_default"

st.set_page_config(page_title="MedAgent -- Тарих", page_icon="📈")
st.title("📈 Тарих және динамика")

engine = get_engine()

PANELS = {
    "Биохимия (негізгі бауыр маркерлері)": list(BIOCHEMISTRY),
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

with Session(engine) as session:
    trend = compute_trend(session, PATIENT_ID, ALL_MARKERS, lookback_n_reports=20)
    ranges = load_ranges(session)

markers_with_data = {code: info for code, info in trend["markers"].items() if info["values"]}

if not markers_with_data:
    st.info("Әзірге жүктелген құжат жоқ. Басты бетте бір анализ немесе құжат жүктеңіз.")
    st.stop()

# --- Section 1: key liver markers overview (default view) ---
st.subheader("Негізгі бауыр көрсеткіштері")
if not key_liver_section(markers_with_data, ranges):
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
    trend_chart(chart_rows(markers_with_data, panel_markers_present, ranges))
    status_lines(markers_with_data, panel_markers_present, ranges)

if trend["meld_na_series"]:
    st.subheader("MELD-Na индексі")
    meld_chart(trend["meld_na_series"])
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
            {"Күні": d.document_date or "—", "Түрі": d.document_type, "Жіктелімі": d.panel_name or d.document_kind or "", "Зертхана": d.lab_name or "", "Файл": d.source_filename}
            for d in by_year_month[ym]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
