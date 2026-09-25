"""
"Ask about your history" chat -- plan Section 11, extra feature 1 (highest
value of the three, since it showcases the dual-RAG design directly).

Queries BOTH Chroma collections via the parameterized search_knowledge MCP
tool -- patient_history (her own documents: discharge summaries, imaging
reports) and clinical_guidelines (sourced medical reference knowledge) --
and grounds a bilingual answer in whichever context is actually retrieved.
Reuses the same Skill (glossary + comorbidity boundary + disclaimer rule)
as generate_explanation_node so terminology and safety framing stay
consistent between the main explanation and follow-up chat.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import or_ as sa_or, select
from sqlalchemy.orm import Session

from data.models import Document, LabValueRow
from data.seed_db import get_engine
from llm_clients import get_traced_anthropic_client
from mcp_server.tools.knowledge_search import search_knowledge

CLAUDE_MODEL = "claude-sonnet-5"
SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "pbc-cirrhosis-explainer"

DISCLAIMER_RU = "Это не является диагнозом. Пожалуйста, обсудите результаты с вашим лечащим врачом."
DISCLAIMER_KZ = "Бұл диагноз емес. Нәтижелерді дәрігеріңізбен талқылаңыз."


def _load_skill_content() -> str:
    parts = []
    for fname in ("SKILL.md", "glossary_kz_ru.md", "tone_templates.md"):
        path = SKILL_DIR / fname
        if path.exists():
            parts.append(f"--- {fname} ---\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def _structured_lab_history_text(patient_id: str, per_marker_limit: int = 3) -> str:
    """Fixes feedback item 8: the chat previously only searched the
    patient_history RAG collection (narrative documents), so a question
    like "менің соңғы АЛТ-м қандай?" could only surface an old mention
    from a discharge summary's free text -- never the actual confirmed
    lab_values rows, which is where real marker numbers live. This pulls
    the last few confirmed readings per marker directly from SQL (cheap,
    deterministic, always available) and includes it in every chat prompt
    rather than gating it behind intent detection."""
    with Session(get_engine()) as session:
        rows = session.execute(
            select(LabValueRow, Document.document_date)
            .join(Document, LabValueRow.document_id == Document.id)
            .where(
                Document.patient_id == patient_id,
                LabValueRow.user_confirmed.is_(True),
                sa_or(LabValueRow.value_numeric.is_not(None), LabValueRow.value_text.is_not(None)),
            )
            .order_by(Document.document_date.desc().nulls_last())
        ).all()

    # Qualitative results (value_text, e.g. "отсутствуют", "1:80") get
    # included here too -- otherwise the chat can't answer about a marker
    # that was never numeric to begin with (same class of gap as the
    # value_text fix in ocr/schema.py).
    by_marker: dict[str, list[tuple[str, float | str, str | None]]] = {}
    for row, doc_date in rows:
        code = row.marker_code or row.marker_name_as_written
        by_marker.setdefault(code, [])
        if len(by_marker[code]) < per_marker_limit:
            shown_value = row.value_numeric if row.value_numeric is not None else row.value_text
            by_marker[code].append((doc_date or "белгісіз күн", shown_value, row.unit))

    if not by_marker:
        return "(нет подтверждённых лабораторных значений в базе)"

    lines = []
    for code, readings in sorted(by_marker.items()):
        readings_str = "; ".join(f"{date}: {value} {unit or ''}".strip() for date, value, unit in readings)
        lines.append(f"- {code}: {readings_str}")
    return "\n".join(lines)


def ask_history(query: str, patient_id: str = "patient_default") -> dict:
    """Returns {"answer_ru": str, "answer_kz": str, "sources": list[dict]}."""
    patient_res = search_knowledge(query=query, collection="patient_history", top_k=4)
    clinical_res = search_knowledge(query=query, collection="clinical_guidelines", top_k=3)

    patient_chunks = patient_res.get("results", [])
    clinical_chunks = clinical_res.get("results", [])
    lab_history_text = _structured_lab_history_text(patient_id)
    has_lab_history = "нет подтверждённых" not in lab_history_text

    if not patient_chunks and not clinical_chunks and not has_lab_history:
        no_data_ru = "Кешіріңіз, сіздің тарихыңызда бұл сұраққа қатысты мәлімет таппадым. / Извините, я не нашёл в вашей истории информации по этому вопросу."
        return {"answer_ru": no_data_ru, "answer_kz": no_data_ru, "sources": []}

    patient_text = "\n\n".join(f"[Сіздің құжатыңыз] {c['chunk_text']}" for c in patient_chunks)
    clinical_text = "\n\n".join(f"[{c.get('source_title')}] {c['chunk_text']}" for c in clinical_chunks)
    skill_content = _load_skill_content()

    prompt = f"""{skill_content}

---

Apply the skill above. The patient/caregiver asked a follow-up question about her own
medical history. Answer ONLY using the context below -- if the context doesn't contain
the answer, say so honestly rather than guessing.

Question: {query}

Her confirmed structured lab values (most reliable source for "what was my
latest X" / "менің соңғы X-м қандай" type questions -- prefer these exact
numbers over anything mentioned in narrative text below, which may be older
or less precise):
{lab_history_text}

Context from her own documents (patient_history):
{patient_text or '(none retrieved)'}

Context from clinical guidelines (clinical_guidelines):
{clinical_text or '(none retrieved)'}

Write TWO complete versions of the answer, KAZAKH FIRST then Russian (Kazakh is
this app's primary language). Use plain, everyday words over clinical jargon where
possible; briefly explain any clinical term you do use. Stay strictly within the
liver/PBC scope -- if her documents mention unrelated conditions (cardiac, renal,
orthopedic, etc.), do not comment on them even if asked; redirect to her doctor.
End both with the disclaimer.

Respond in this exact format:
KZ: <kazakh answer>
RU: <russian answer>"""

    client = get_traced_anthropic_client()
    # 3000 was still too low: real-usage bug found after adding the
    # structured-lab-values context (item 8 fix) and the reranker (wider RAG
    # context) -- a real query returned a completely empty answer, traced to
    # Claude Sonnet 5 spending part of the max_tokens budget on internal
    # "thinking" tokens (visible in resp.usage.output_tokens_details) before
    # any output text, which on a larger prompt sometimes ate the whole
    # budget (stop_reason == max_tokens with zero text blocks). Raised to
    # 6000 for headroom; the truncation-note fallback below still covers the
    # remaining edge case.
    resp = client.messages.create(model=CLAUDE_MODEL, max_tokens=6000, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if b.type == "text")

    if not text.strip():
        # Belt-and-suspenders for the same empty-answer failure mode as
        # above, in case max_tokens=6000 still isn't enough for a
        # particularly large retrieved context -- an honest "couldn't
        # answer, try again" beats silently showing just the disclaimer.
        retry_msg_kz = "Кешіріңіз, жауап дайындай алмадым -- сұрағыңызды қайта, басқаша тұжырымдап көріңізші."
        retry_msg_ru = "Извините, не удалось подготовить ответ -- попробуйте переформулировать вопрос."
        return {"answer_ru": retry_msg_ru, "answer_kz": retry_msg_kz, "sources": []}

    ru, kz = "", ""
    if "RU:" in text and "KZ:" in text:
        kz = text.split("KZ:")[1].split("RU:")[0].strip()
        ru = text.split("RU:")[1].strip()
    else:
        ru = text

    if "не является диагнозом" not in ru.lower():
        ru += "\n\n" + DISCLAIMER_RU
    if "диагноз емес" not in kz.lower():
        kz += "\n\n" + DISCLAIMER_KZ

    sources = [{"type": "patient_history", **c} for c in patient_chunks] + [
        {"type": "clinical_guidelines", **c} for c in clinical_chunks
    ]
    return {"answer_ru": ru, "answer_kz": kz, "sources": sources}
