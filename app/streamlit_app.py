"""
MedAgent Streamlit app -- the user-facing frontend (plan Section 11 ТЗ
requirement: web frontend, not CLI).

Day 3's headless test (graph/test_headless.py) proved the interrupt()/
Command(resume=...) mechanic works across separate process invocations.
This app proves the harder case: it must work across Streamlit's
rerun-on-every-interaction model, which is why the graph + its SqliteSaver
checkpointer are built ONCE (st.cache_resource) and thread_id is the only
thing threading state across reruns -- every button click here is really
"resume this specific paused graph run from disk," not an in-memory
continuation.
"""
from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from graph.build_graph import CHECKPOINT_DB, build_graph

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="MedAgent", page_icon="🩺", layout="centered")

SEVERITY_COLOR = {
    "critical": "🔴",
    "worsening": "🟡",
    "improving": "🟢",
    "stable": "🟢",
}
SEVERITY_LABEL_RU = {
    "critical": "Требует внимания врача",
    "worsening": "Ухудшение",
    "improving": "Улучшение",
    "stable": "Стабильно",
}


@st.cache_resource
def get_checkpointer_and_graph():
    """Builds the checkpointer from a raw sqlite3.Connection rather than
    SqliteSaver.from_conn_string()'s context-manager form.

    Bug found during Day 4 browser testing: manually calling that context
    manager's __enter__() and caching just the checkpointer left the
    contextmanager generator itself unreferenced -- Python garbage-collected
    it, which ran the generator's cleanup/__exit__ and closed the underlying
    connection, so the very next Streamlit rerun hit
    "sqlite3.ProgrammingError: Cannot operate on a closed database."
    A directly-constructed, explicitly-retained sqlite3.Connection (with
    check_same_thread=False, since Streamlit's ScriptRunner can execute
    reruns on different threads) has no such hidden lifecycle."""
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = build_graph(checkpointer=checkpointer)
    return graph


graph = get_checkpointer_and_graph()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "result" not in st.session_state:
    st.session_state.result = None

st.title("🩺 MedAgent")
st.caption("Первичный билиарный холангит / цирроз — анализ нәтижелерін түсіндіру")

uploaded_file = st.file_uploader(
    "Анализ, выписка немесе УЗИ/FibroScan суретін/PDF-ін жүктеңіз",
    type=["jpg", "jpeg", "png", "pdf"],
)

if uploaded_file is not None:
    if st.session_state.get("_last_uploaded_name") != uploaded_file.name:
        # New file -> new thread, fresh graph run.
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{uploaded_file.name}"
        dest.write_bytes(uploaded_file.getvalue())

        thread_id = f"patient_default:{uuid.uuid4().hex[:12]}"
        st.session_state.thread_id = thread_id
        st.session_state._last_uploaded_name = uploaded_file.name

        with st.spinner("Құжат оқылуда..."):
            config = {"configurable": {"thread_id": thread_id}}
            result = graph.invoke(
                {"patient_id": "patient_default", "raw_file_path": str(dest)}, config=config
            )
        st.session_state.result = result
        st.rerun()

result = st.session_state.result

if result is not None:
    config = {"configurable": {"thread_id": st.session_state.thread_id}}

    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        kind = payload.get("kind")

        if kind == "confirm_lab_extraction":
            st.subheader("Оқылған мәндерді тексеріңіз")
            if payload.get("injection_detected"):
                st.warning("Құжатта күдікті мәтін табылды -- мұқият тексеріңіз.")
            inconsistent = set(payload.get("inconsistent_rows", []))
            if inconsistent:
                st.warning(f"Бұл жолдар өз референс диапазонынан тыс, бірақ жалаушасыз: {', '.join(inconsistent)}")

            values = payload["extraction"]["values"]
            df = pd.DataFrame(values)
            edited_df = st.data_editor(df, num_rows="dynamic", key="edit_extraction")

            col1, col2 = st.columns(2)
            if col1.button("✅ Растаймын / Подтверждаю", type="primary"):
                # pandas turns a None in a mixed-type (or all-None, inferred
                # float64) column into float NaN; Pydantic's `str | None`
                # fields reject a NaN float outright. DataFrame.where(...,
                # None) does NOT fix this -- assigning None back into an
                # already-float64 column just becomes NaN again (dtype
                # coercion), which is what real browser testing caught on
                # the first attempted fix. Cleaning at the record/cell level
                # after to_dict() sidesteps DataFrame dtype coercion entirely.
                raw_records = edited_df.to_dict(orient="records")
                cleaned_records = [
                    {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}
                    for row in raw_records
                ]
                edited_extraction = dict(payload["extraction"])
                edited_extraction["values"] = cleaned_records
                with st.spinner("Жалғасуда..."):
                    new_result = graph.invoke(
                        Command(resume={"approved": True, "extraction": edited_extraction}), config=config
                    )
                st.session_state.result = new_result
                st.rerun()
            if col2.button("🔄 Қайта жүктеу / Загрузить заново"):
                st.session_state.thread_id = None
                st.session_state.result = None
                st.session_state._last_uploaded_name = None
                st.rerun()

        elif kind == "confirm_save":
            st.subheader("Түсіндірмені сақтауды растайсыз ба?")
            st.write(payload.get("explanation_ru", "")[:300] + "...")
            if st.button("💾 Сақтау / Сохранить", type="primary"):
                with st.spinner("Сақталуда..."):
                    new_result = graph.invoke(Command(resume={"approved": True}), config=config)
                st.session_state.result = new_result
                st.rerun()

    else:
        # Graph reached END.
        if result.get("document_type") == "narrative":
            st.success("Құжат оқылды және жеке тарихқа қосылды.")
            st.write(f"Түрі: {result.get('document_kind')}, күні: {result.get('document_date')}")
        else:
            severity = result.get("severity", "stable")
            st.markdown(f"## {SEVERITY_COLOR.get(severity, '⚪')} {SEVERITY_LABEL_RU.get(severity, severity)}")

            tab_ru, tab_kz = st.tabs(["Орысша", "Қазақша"])
            with tab_ru:
                st.write(result.get("explanation_ru", ""))
            with tab_kz:
                st.write(result.get("explanation_kz", ""))

            meld_series = result.get("trend", {}).get("meld_na_series", [])
            if meld_series:
                st.subheader("MELD-Na")
                st.line_chart(pd.DataFrame(meld_series).set_index("date"))

        if st.button("➕ Жаңа құжат жүктеу"):
            st.session_state.thread_id = None
            st.session_state.result = None
            st.session_state._last_uploaded_name = None
            st.rerun()
