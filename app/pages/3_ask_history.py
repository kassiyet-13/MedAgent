"""
"Ask about your history" chat page -- plan Section 11, extra feature 1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from chat.followup_chat import ask_history

st.set_page_config(page_title="MedAgent -- Сұрақ қою", page_icon="💬")
st.title("💬 Тарихыңыз туралы сұраңыз")
st.caption("Мысалы: «соңғы FibroScan нәтижесі қандай болды?», «неге дәрі ауыстырылды?»")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for turn in st.session_state.chat_history:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        tab_kz, tab_ru = st.tabs(["Қазақша", "Орысша"])
        with tab_kz:
            st.write(turn["answer_kz"])
        with tab_ru:
            st.write(turn["answer_ru"])
        if turn["sources"]:
            with st.expander(f"Дереккөздер ({len(turn['sources'])})"):
                for s in turn["sources"]:
                    st.caption(f"[{s['type']}] score={s.get('similarity_score', 0):.2f} -- {s['chunk_text'][:150]}...")

question = st.chat_input("Сұрағыңызды жазыңыз...")
if question:
    with st.spinner("Іздеп жатыр..."):
        result = ask_history(question)
    st.session_state.chat_history.append(
        {
            "question": question,
            "answer_ru": result["answer_ru"],
            "answer_kz": result["answer_kz"],
            "sources": result["sources"],
        }
    )
    st.rerun()
