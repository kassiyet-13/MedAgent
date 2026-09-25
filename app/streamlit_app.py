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
from sqlalchemy.orm import Session

from data.dedup import compute_file_hash, find_existing_document
from data.models import Assessment, ReferenceRange
from data.seed_db import get_engine
from graph.build_graph import CHECKPOINT_DB, build_graph
from mcp_server.tools.trend import compute_trend
from ocr.marker_suggest import add_marker_entry, suggest_marker_entry
from skills.glossary import get_marker_blurb

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="MedAgent", page_icon="🩺", layout="wide")

SEVERITY_COLOR = {
    "critical": "🔴",
    "worsening": "🟡",
    "improving": "🟢",
    "stable": "🟢",
}
SEVERITY_LABEL_KZ = {
    "critical": "Дәрігердің назарын қажет етеді",
    "worsening": "Нашарлау",
    "improving": "Жақсару",
    "stable": "Тұрақты",
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


def _recover_from_checkpoint(thread_id: str):
    """Reconstruct a result dict from LangGraph's own durable checkpoint,
    for when Streamlit's in-memory session_state was lost.

    Real-usage bug report: after leaving the tab backgrounded for about a
    minute, the confirmation table and everything on screen vanished. Root
    cause: st.session_state lives only in server memory tied to one specific
    websocket session -- a long-backgrounded tab can get discarded by the
    browser and reconnect as a genuinely NEW session, silently wiping it.
    The LangGraph checkpoint (data/langgraph_checkpoints.db) is durable and
    keyed only by thread_id, so recovery reads from there instead of
    trusting session_state alone -- thread_id itself is kept in the URL
    query params (which DO survive a reload) specifically to make this
    possible."""
    config = {"configurable": {"thread_id": thread_id}}
    snap = graph.get_state(config)
    if not snap.values:
        return None  # unknown thread_id -- nothing to recover

    has_interrupt = any(t.interrupts for t in snap.tasks)
    if has_interrupt:
        interrupt_obj = next(t.interrupts[0] for t in snap.tasks if t.interrupts)
        return {**snap.values, "__interrupt__": (interrupt_obj,)}
    if not snap.next:
        return dict(snap.values)  # graph ran to completion
    return "broken"  # paused mid-run at a non-interrupt node (e.g. process was killed)


if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "result" not in st.session_state:
    st.session_state.result = None
if "uploader_key" not in st.session_state:
    # Bumped on every reset so st.file_uploader gets a brand-new widget
    # identity and forgets its previously selected file. Real-usage bug
    # report: clicking "Жаңа құжат жүктеу" cleared session_state but the
    # uploader widget itself kept the old file attached (Streamlit does not
    # reset a file_uploader's selection just because session_state changed
    # around it) -- with the SAME file still "selected" and
    # _last_uploaded_file_id now cleared, the app silently reprocessed the
    # OLD file instead of showing a blank upload screen.
    st.session_state.uploader_key = 0

if st.session_state.result is None:
    qp_thread_id = st.query_params.get("thread_id")
    if qp_thread_id:
        recovered = _recover_from_checkpoint(qp_thread_id)
        if recovered == "broken":
            st.warning("Алдыңғы сессия аяқталмаған күйде үзілген. Құжатты қайта жүктеңіз.")
            st.query_params.clear()
        elif recovered is not None:
            st.session_state.thread_id = qp_thread_id
            st.session_state.result = recovered
            st.session_state._last_uploaded_file_id = "recovered"  # block a spurious re-trigger below

st.title("🩺 MedAgent")
st.caption("Первичный билиарный холангит / цирроз — анализ нәтижелерін түсіндіру")

if st.session_state.result is None:
    # Quick history snapshot on the idle landing screen -- feedback item 1:
    # "Landing page ... өте тартымсыз, анализді жүкте деп тұрады ... Бәлкім
    # басты бетке ... трендті осында қосамыз ба?" Kept intentionally light
    # (last assessment + a small key-marker chart), the full breakdown
    # stays on the History/trends page rather than duplicating it here.
    with Session(get_engine()) as _s:
        _last_assessment = (
            _s.query(Assessment).order_by(Assessment.created_at.desc()).first()
        )
    if _last_assessment:
        st.markdown(
            f"**Соңғы жағдай:** {SEVERITY_COLOR.get(_last_assessment.overall_status, '⚪')} "
            f"{SEVERITY_LABEL_KZ.get(_last_assessment.overall_status, _last_assessment.overall_status)}"
        )
        with Session(get_engine()) as _s:
            _trend = compute_trend(_s, "patient_default", ["ALT", "AST", "BILI_TOTAL"], lookback_n_reports=5)
        _frames = []
        for _code in ("ALT", "AST", "BILI_TOTAL"):
            _vals = _trend["markers"].get(_code, {}).get("values", [])
            if _vals:
                _df = pd.DataFrame(_vals).rename(columns={"value": _code}).set_index("date")[[_code]]
                _frames.append(_df)
        if _frames:
            _combined = _frames[0]
            for _f in _frames[1:]:
                _combined = _combined.join(_f, how="outer")
            st.line_chart(_combined, height=180)
        st.caption("Толық тарих пен динамика -- сол жақтағы «history trends» бетінде.")
        st.divider()

uploaded_file = st.file_uploader(
    "Анализ, выписка немесе УЗИ/FibroScan суретін/PDF-ін жүктеңіз",
    type=["jpg", "jpeg", "png", "pdf"],
    key=f"uploader_{st.session_state.uploader_key}",
)

if uploaded_file is not None:
    # Track by file_id, not name -- Streamlit assigns a fresh file_id to
    # every upload instance even when the same filename is re-selected
    # (e.g. testing with the same sample file twice, or Remove+Add with the
    # same file). Tracking by name alone silently skipped reprocessing in
    # that case -- real-usage bug report: "second upload button doesn't work."
    if st.session_state.get("_last_uploaded_file_id") != uploaded_file.file_id:
        file_bytes = uploaded_file.getvalue()
        content_hash = compute_file_hash(file_bytes)

        # Dedup check -- user question: "мен бір анализді қайта қайта
        # жүктесем система оны жаңадан сақтай ма?" (answer was: yes, always,
        # no check existed). Checked BEFORE spending any OCR/LLM call, not
        # after -- cheaper and catches the exact problem this session's own
        # repeated test uploads demonstrated.
        with Session(get_engine()) as _s:
            existing_doc = find_existing_document(_s, "patient_default", content_hash)
        force = st.session_state.get("_force_duplicate_upload") == uploaded_file.file_id

        if existing_doc is not None and not force:
            when = existing_doc.document_date or existing_doc.uploaded_at.date().isoformat()
            st.warning(f"Бұл файл бұрын жүктелген (күні: {when}). Қайта жүктеу керек пе?")
            col_a, col_b = st.columns(2)
            if col_a.button("✅ Бәрібір жүктеу", key=f"force_dup_{uploaded_file.file_id}"):
                st.session_state._force_duplicate_upload = uploaded_file.file_id
                st.rerun()
            if col_b.button("❌ Бас тарту", key=f"cancel_dup_{uploaded_file.file_id}"):
                st.session_state.uploader_key += 1
                st.rerun()
        else:
            # New file -> new thread, fresh graph run.
            dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{uploaded_file.name}"
            dest.write_bytes(file_bytes)

            thread_id = f"patient_default:{uuid.uuid4().hex[:12]}"
            st.session_state.thread_id = thread_id
            st.session_state._last_uploaded_file_id = uploaded_file.file_id
            st.session_state.pop("_force_duplicate_upload", None)
            st.query_params["thread_id"] = thread_id

            with st.spinner("Құжат оқылуда..."):
                config = {"configurable": {"thread_id": thread_id}}
                result = graph.invoke(
                    {"patient_id": "patient_default", "raw_file_path": str(dest), "content_hash": content_hash},
                    config=config,
                )
            st.session_state.result = result
            st.rerun()

def _render_lab_result(result: dict) -> None:
    """Shared between the pre-save (confirm_save interrupt) and post-save
    (graph reached END) views -- feedback: a separate, Russian-only,
    truncated-text confirmation screen before the real result was confusing;
    the user wants to see the actual full status/explanation first and save
    from that same screen."""
    severity = result.get("severity", "stable")
    st.markdown(f"## {SEVERITY_COLOR.get(severity, '⚪')} {SEVERITY_LABEL_KZ.get(severity, severity)}")

    # Kazakh shown first -- feedback item 2: "Маған ең бірінші керек
    # тіл ол қазақша. Бірінші тіл барлық жерде қазақша болуы керек."
    tab_kz, tab_ru = st.tabs(["Қазақша", "Орысша"])
    with tab_kz:
        st.write(result.get("explanation_kz", ""))
    with tab_ru:
        st.write(result.get("explanation_ru", ""))

    meld_series = result.get("trend", {}).get("meld_na_series", [])
    if meld_series:
        st.subheader("MELD-Na")
        st.line_chart(pd.DataFrame(meld_series).set_index("date"))

    # Glossary cards -- feedback item 3: plain-language "what is this
    # marker and why does it matter" per analyzed value, on demand
    # rather than dumped into the main explanation text.
    extraction = result.get("extraction", {})
    values = extraction.get("values", [])
    if values:
        st.subheader("Көрсеткіштер туралы қысқаша")
        for v in values:
            blurb = get_marker_blurb(v.get("marker_code"), lang="kz")
            if blurb:
                # Qualitative results (e.g. "отсутствуют", "1:80") have no
                # numeric value -- show value_text instead rather than a
                # blank/"None" reading, per the value_text fix above.
                shown_value = v.get("value") if v.get("value") is not None else v.get("value_text")
                label = f"{v.get('marker_name_as_written')}: {shown_value} {v.get('unit') or ''}"
                with st.expander(label):
                    st.write(blurb)


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

            # Document-level metadata above the values table -- feedback:
            # "файлды анализді оқып болған соң метаданныйларды кестенің
            # жоғары жағына шығаршы" (show the document metadata above the
            # table). Editable, same reasoning as the values table itself --
            # document_date extraction has already had one real bug found
            # (letterhead date vs actual registration date), so letting the
            # user correct it here rather than only being able to fix
            # individual marker values makes sense.
            meta_col1, meta_col2 = st.columns(2)
            edited_document_date = meta_col1.text_input(
                "Тіркеу күні (registration date)",
                value=payload["extraction"].get("document_date") or "",
                key=f"doc_date_{st.session_state.thread_id}",
            )
            edited_lab_name = meta_col2.text_input(
                "Зертхана атауы (lab name)",
                value=payload["extraction"].get("lab_name") or "",
                key=f"lab_name_{st.session_state.thread_id}",
            )
            st.caption(f"Модельдің жалпы сенімділігі: {payload['extraction'].get('overall_confidence', '—')}")

            values = payload["extraction"]["values"]
            df = pd.DataFrame(values)

            # Out-of-range flag column -- feedback: highlight abnormal values
            # with a color. st.data_editor (needed here since the table must
            # stay editable) does NOT support cell/row background styling the
            # way read-only st.dataframe does (a Streamlit limitation, not a
            # choice) -- a status column is the equivalent that actually
            # works in an editable grid. 🔴 red matches both real lab-report
            # convention for an abnormal flag and this app's own severity
            # color scheme (SEVERITY_COLOR above uses 🔴 for "critical").
            def _status(row) -> str:
                v, lo, hi = row.get("value"), row.get("lab_ref_low"), row.get("lab_ref_high")
                if v is None or lo is None or hi is None:
                    return ""
                return "🔴" if not (lo <= v <= hi) else "🟢"

            if not df.empty:
                df.insert(0, "Күй", df.apply(_status, axis=1))

            # No internal scrollbar -- feedback: "барлық көрсеткіштерді
            # сиятындай етіп кеңейт" (expand so every row fits, no
            # scrolling). st.data_editor defaults to a fixed viewport height;
            # sizing it to the actual row count (~35px/row, Streamlit's own
            # row height) makes every row visible without scrolling.
            table_height = min(len(df) + 1, 60) * 35 + 3
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                key="edit_extraction",
                use_container_width=True,
                height=table_height,
                column_config={"Күй": st.column_config.TextColumn("Күй", disabled=True, width="small")},
            )
            if "Күй" in edited_df.columns:
                edited_df = edited_df.drop(columns=["Күй"])

            # Semi-automated new-marker onboarding -- user question: "сонда
            # әркез мен өзім қосып отыруым керек пе?" (do I have to add every
            # new marker by hand every time?). Fully automatic was rejected
            # for safety (an LLM silently writing its own "normal range" into
            # the clinical reference DB is a real risk, same reasoning as why
            # human_confirm_node is unconditional) -- instead this drafts a
            # candidate entry for the user to review/edit/approve right here.
            # name -> newly-approved marker_code, so an already-approved
            # marker (a) drops out of the "unmatched" list on THIS SAME
            # screen without needing a rerun/reupload, and (b) actually gets
            # written onto this document's saved values on confirm -- real
            # bug found via feedback: add_marker_entry() only writes
            # reference_ranges.json/DB, it never touched the CURRENT row's
            # marker_code in edited_df/payload, so a marker approved here
            # kept showing up as "unmatched" forever on this document even
            # though it now exists in the reference DB.
            approved_map = st.session_state.setdefault("_approved_marker_map", {})
            unmatched = [
                row for row in edited_df.to_dict(orient="records")
                if (not row.get("marker_code") or (isinstance(row.get("marker_code"), float) and math.isnan(row.get("marker_code"))))
                and row.get("marker_name_as_written") not in approved_map
            ]
            if unmatched:
                st.divider()
                st.caption("Танылмаған көрсеткіштер -- дерекқорға қосу үшін ұсыныс жасауға болады:")
                suggestions = st.session_state.setdefault("_marker_suggestions", {})
                for row in unmatched:
                    name = row.get("marker_name_as_written") or "(атаусыз)"
                    with st.expander(f"❔ {name}"):
                        if name not in suggestions:
                            if st.button("Ұсыныс жасау", key=f"suggest_{name}_{st.session_state.thread_id}"):
                                with Session(get_engine()) as session:
                                    existing_codes = [r[0] for r in session.query(ReferenceRange.marker_code).all()]
                                with st.spinner("Дайындалуда..."):
                                    suggestions[name] = suggest_marker_entry(
                                        marker_name_as_written=name,
                                        unit=row.get("unit"),
                                        lab_ref_low=row.get("lab_ref_low"),
                                        lab_ref_high=row.get("lab_ref_high"),
                                        existing_codes=existing_codes,
                                    )
                                st.rerun()
                        else:
                            draft = suggestions[name]
                            # .get() with a fallback everywhere here -- forced
                            # tool_choice does not strictly guarantee every
                            # "required" schema field actually comes back
                            # populated (real-usage bug: a second marker's
                            # suggestion came back without cirrhosis_note,
                            # crashing this screen with a bare KeyError).
                            draft["marker_code"] = st.text_input("Код", value=draft.get("marker_code", ""), key=f"code_{name}")
                            draft["marker_name_kz"] = st.text_input("Атауы (қазақша)", value=draft.get("marker_name_kz", ""), key=f"kz_{name}")
                            draft["marker_name_ru"] = st.text_input("Атауы (орысша)", value=draft.get("marker_name_ru", ""), key=f"ru_{name}")
                            draft["unit"] = st.text_input("Бірлігі", value=draft.get("unit") or "", key=f"unit_{name}")
                            c1, c2 = st.columns(2)
                            draft["normal_low"] = c1.number_input("Норма (төмен)", value=draft.get("normal_low") or 0.0, key=f"lo_{name}")
                            draft["normal_high"] = c2.number_input("Норма (жоғары)", value=draft.get("normal_high") or 0.0, key=f"hi_{name}")
                            draft["cirrhosis_note"] = st.text_area("Ескертпе", value=draft.get("cirrhosis_note", ""), key=f"note_{name}")
                            if st.button("✅ Дерекқорға қосу", key=f"approve_{name}_{st.session_state.thread_id}"):
                                add_marker_entry(draft)
                                approved_map[name] = draft["marker_code"]
                                st.success(
                                    f"{draft['marker_code']} қосылды -- норма/тренд бетінде бірден көрінеді. "
                                    "Жаңа құжаттарда автоматты танылуы үшін серверді қайта іске қосыңыз."
                                )
                                del suggestions[name]
                                st.rerun()
                st.divider()

            col1, col2 = st.columns(2)
            if col1.button("✅ Растаймын / Подтверждаю", type="primary", key=f"confirm_{st.session_state.thread_id}"):
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
                # Apply any marker codes approved via "Дерекқорға қосу" above
                # -- without this, a newly-approved code never makes it into
                # THIS document's saved lab_values (reference lookup/trend
                # would still treat the row as unmatched even though the
                # reference DB now has the marker).
                for record in cleaned_records:
                    if not record.get("marker_code"):
                        approved_code = approved_map.get(record.get("marker_name_as_written"))
                        if approved_code:
                            record["marker_code"] = approved_code
                edited_extraction = dict(payload["extraction"])
                edited_extraction["values"] = cleaned_records
                edited_extraction["document_date"] = edited_document_date or None
                edited_extraction["lab_name"] = edited_lab_name or None
                with st.spinner("Жалғасуда..."):
                    new_result = graph.invoke(
                        Command(resume={"approved": True, "extraction": edited_extraction}), config=config
                    )
                st.session_state.result = new_result
                st.rerun()
            if col2.button("🔄 Қайта жүктеу / Загрузить заново", key=f"reupload_{st.session_state.thread_id}"):
                st.session_state.thread_id = None
                st.session_state.result = None
                st.session_state._last_uploaded_file_id = None
                st.session_state.uploader_key += 1
                st.query_params.clear()
                st.rerun()

        elif kind == "confirm_save":
            _render_lab_result(result)
            st.divider()
            if st.button("💾 Сақтау / Сохранить", type="primary", key=f"save_{st.session_state.thread_id}"):
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
            _render_lab_result(result)

        if st.button("➕ Жаңа құжат жүктеу"):
            st.session_state.thread_id = None
            st.session_state.result = None
            st.session_state._last_uploaded_file_id = None
            st.session_state.uploader_key += 1
            st.query_params.clear()
            st.rerun()
