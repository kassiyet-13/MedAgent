"""
MedAgent Streamlit entrypoint -- navigation only.

Run: streamlit run app/streamlit_app.py

Explicit st.navigation instead of Streamlit's automatic pages/ discovery,
per feedback: the sidebar menu showed raw English file names ("streamlit
app", "history trends", "batch upload") -- this app's primary language is
Kazakh, so every menu entry gets a proper Kazakh title here. The upload
page itself lives in pages/1_lab_upload.py.
"""
import streamlit as st

pg = st.navigation(
    [
        st.Page("pages/1_lab_upload.py", title="Анализ жүктеу", icon="🩺", default=True),
        st.Page("pages/5_batch_upload.py", title="Выписка және басқа құжаттар", icon="📚"),
        st.Page("pages/2_history_trends.py", title="Тарих және динамика", icon="📈"),
        st.Page("pages/3_ask_history.py", title="Тарих бойынша сұрақ қою", icon="💬"),
        st.Page("pages/4_checkin.py", title="Апталық тексеру", icon="📝"),
    ]
)
pg.run()
