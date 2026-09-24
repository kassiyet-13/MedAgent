"""
Batch upload page -- feedback follow-up: the patient/caregiver often has
several discharge summaries / УЗИ / FibroScan reports to digitize at once,
not just one lab panel at a time.

Deliberately narrative-only. Document type is decided per-file, automatically,
by the same content-based classify_document_type_node the single-upload flow
uses (a cheap vision-LLM call: "numeric lab table or free-text narrative?") --
NOT by which page/button the file was uploaded through. That's exactly why a
batch flow is safe to offer for narrative documents but not for lab panels:
lab extraction accuracy is not reliable enough to skip human confirmation
(see graph/nodes.py::human_confirm_node -- it runs unconditionally, per the
Day-2 finding that self-reported OCR confidence was not trustworthy). If a
file in the batch classifies as lab_panel, this page does NOT try to
auto-confirm it -- the graph run is simply left paused at its interrupt
(same as if the user had walked away mid-confirmation on the main page) and
the user is told to upload that file individually instead.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.orm import Session

from data.dedup import compute_file_hash, find_existing_document
from data.seed_db import get_engine
from graph.build_graph import CHECKPOINT_DB, build_graph
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

PATIENT_ID = "patient_default"
ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="MedAgent -- Көп құжат жүктеу", page_icon="📚")
st.title("📚 Бірнеше құжатты бірден жүктеу")

st.caption(
    "Тек **выписка, УЗИ немесе FibroScan қорытындысы сияқты құжаттарға** арналған -- "
    "олар автоматты өңделеді, растаудың қажеті жоқ. Әр файлдың түрін жүйе өзі "
    "мазмұны бойынша анықтайды (файл атауына немесе осы бетке қарап емес)."
)
with st.expander("Құжат түрі қалай анықталады?"):
    st.write(
        "Әр жүктелген файл алдымен қысқа тексеруден өтеді: ол сандық "
        "кесте (анализ) па, әлде еркін мәтін (выписка/қорытынды) ма деп. "
        "**Анализ (lab-панель) анықталса, бұл жерде автоматты өңделмейді** -- "
        "лаб-мәндер дәлдігі әрдайым адаммен расталуы керек (бұрынғы тестілеуде "
        "модель өзін 95% сенімді деп есептеп, дұрыс емес мән бергені анықталды). "
        "Ондай файл табылса, оны негізгі бетте жеке-жеке жүктеп, кестені "
        "тексеріп растау керек болады."
    )


@st.cache_resource
def get_batch_graph():
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return build_graph(checkpointer=checkpointer)


graph = get_batch_graph()

uploaded_files = st.file_uploader(
    "Құжаттарды таңдаңыз (бірнешеуін бірден таңдауға болады)",
    type=["jpg", "jpeg", "png", "pdf"],
    accept_multiple_files=True,
    key="batch_uploader",
)

if uploaded_files and st.button("Барлығын өңдеу", type="primary"):
    results = []
    progress = st.progress(0.0, text="Басталды...")
    for i, uf in enumerate(uploaded_files):
        progress.progress(i / len(uploaded_files), text=f"Өңделуде: {uf.name}")
        file_bytes = uf.getvalue()
        content_hash = compute_file_hash(file_bytes)

        # Dedup check -- same reasoning as the main upload page: skip an
        # exact re-upload before spending an OCR/LLM call on it. Batch mode
        # has no per-file confirmation step, so a duplicate is auto-skipped
        # (reported, not silently dropped) rather than asking to override.
        with Session(get_engine()) as _s:
            existing_doc = find_existing_document(_s, PATIENT_ID, content_hash)
        if existing_doc is not None:
            when = existing_doc.document_date or existing_doc.uploaded_at.date().isoformat()
            results.append({"file": uf.name, "status": "duplicate", "detail": f"Бұрын жүктелген (күні: {when}) -- өткізіп жіберілді."})
            continue

        dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{uf.name}"
        dest.write_bytes(file_bytes)
        thread_id = f"{PATIENT_ID}:{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = graph.invoke(
                {"patient_id": PATIENT_ID, "raw_file_path": str(dest), "content_hash": content_hash}, config=config
            )
        except Exception as e:
            results.append({"file": uf.name, "status": "error", "detail": str(e)})
            continue

        if "__interrupt__" in result:
            results.append(
                {
                    "file": uf.name,
                    "status": "needs_manual",
                    "detail": "Бұл анализ (lab-панель) сияқты -- негізгі бетте жеке жүктеп растаңыз.",
                }
            )
        elif result.get("document_type") == "narrative":
            results.append(
                {
                    "file": uf.name,
                    "status": "ok",
                    "detail": (
                        f"{result.get('document_kind') or 'құжат'} ретінде тіркелді, "
                        f"күні: {result.get('document_date') or 'белгісіз'}, "
                        f"{result.get('_patient_history_chunks_added', 0)} үзінді қосылды."
                    ),
                }
            )
        else:
            results.append({"file": uf.name, "status": "unknown", "detail": "Күтпеген нәтиже."})

    progress.progress(1.0, text="Дайын")
    st.divider()
    st.subheader("Нәтиже")
    for r in results:
        icon = {"ok": "✅", "needs_manual": "⚠️", "error": "❌", "unknown": "❔", "duplicate": "⏭️"}[r["status"]]
        st.markdown(f"{icon} **{r['file']}** -- {r['detail']}")
