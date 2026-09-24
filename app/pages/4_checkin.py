"""
Symptom/mood check-in page -- plan Section 11, extra feature 3.
Self-reported, no external data source; confusion_level is West-Haven-
inspired (0-4) since it's clinically relevant to hepatic encephalopathy in
cirrhosis (plan Section 5a/10).
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.orm import Session

from data.models import Checkin
from data.seed_db import get_engine

PATIENT_ID = "patient_default"

st.set_page_config(page_title="MedAgent -- Апталық тексеру", page_icon="📝")
st.title("📝 Апталық көңіл-күй/симптом тексеруі")

engine = get_engine()

with st.form("checkin_form"):
    fatigue = st.slider("Шаршау деңгейі (1 = жоқ, 5 = өте қатты)", 1, 5, 3)
    swelling = st.checkbox("Аяқ/іш ісінуі бар ма?")
    appetite = st.slider("Тәбет (1 = нашар, 5 = жақсы)", 1, 5, 3)
    confusion = st.select_slider(
        "Ой-саналылық/зейін (West-Haven негізінде)",
        options=[0, 1, 2, 3, 4],
        value=0,
        format_func=lambda x: {
            0: "0 -- қалыпты",
            1: "1 -- жеңіл ұйқышылдық/зейін төмендеуі",
            2: "2 -- дезориентация, летаргия",
            3: "3 -- қатты шатасу",
            4: "4 -- ояна алмау",
        }[x],
    )
    notes = st.text_area("Қосымша ескертпе (міндетті емес)")
    submitted = st.form_submit_button("Сақтау")

    if submitted:
        with Session(engine) as session:
            session.add(
                Checkin(
                    id=uuid.uuid4().hex,
                    patient_id=PATIENT_ID,
                    fatigue_level=fatigue,
                    swelling=swelling,
                    appetite_level=appetite,
                    confusion_level=confusion,
                    notes=notes or None,
                )
            )
            session.commit()
        st.success("Сақталды!")
        if confusion >= 2:
            st.warning("Зейін/ой-саналылық өзгерісі ​бауыр энцефалопатиясының белгісі болуы мүмкін -- дәрігермен жақын арада байланысуды ұсынамыз.")
        st.rerun()

with Session(engine) as session:
    checkins = (
        session.query(Checkin)
        .filter(Checkin.patient_id == PATIENT_ID)
        .order_by(Checkin.created_at.asc())
        .all()
    )

if checkins:
    st.subheader("Тарих")
    df = pd.DataFrame(
        [
            {
                "Күні": c.created_at,
                "Шаршау": c.fatigue_level,
                "Тәбет": c.appetite_level,
                "Ой-саналылық": c.confusion_level,
                "Ісіну": "Иә" if c.swelling else "Жоқ",
            }
            for c in checkins
        ]
    )
    st.line_chart(df.set_index("Күні")[["Шаршау", "Тәбет", "Ой-саналылық"]])
    st.dataframe(df, use_container_width=True)
