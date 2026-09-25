"""
LangGraph node functions. Plan Section 2.

Day 4 update: generate_explanation_node now loads the pbc-cirrhosis-explainer
Skill (skills/pbc-cirrhosis-explainer/) -- SKILL.md's instructions, the
bilingual glossary, and the tone templates -- and injects them into this
ONE node's prompt only (progressive disclosure: no other node pays the
context cost of this content).
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from langgraph.types import interrupt
from sqlalchemy.orm import Session

from data.dedup import compute_file_hash
from data.models import Assessment, Document, EscalationLogEntry, LabValueRow
from data.seed_db import get_engine
from guardrails.injection_check import check_for_injection
from guardrails.pii_scrub import scrub
from llm_clients import get_traced_anthropic_client
from mcp_server.tools.reference_ranges import get_reference_ranges as _get_reference_ranges
from mcp_server.tools.trend import compute_trend as _compute_trend
from mcp_server.tools.knowledge_search import search_knowledge as _search_knowledge
from ocr.schema import LabExtraction, NarrativeExtraction
from ocr.vision_extract import (
    classify_document_type,
    extract_lab_panel_with_fallback,
    extract_narrative,
)
from rag.ingest_patient_doc import ingest_patient_document

_engine = get_engine()
CLAUDE_MODEL = "claude-sonnet-5"

DISCLAIMER_RU = "Это не является диагнозом. Пожалуйста, обсудите результаты с вашим лечащим врачом."
DISCLAIMER_KZ = "Бұл диагноз емес. Нәтижелерді дәрігеріңізбен талқылаңыз."
DISCLAIMER_MARKER_RU = "не является диагнозом"
DISCLAIMER_MARKER_KZ = "диагноз емес"

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "pbc-cirrhosis-explainer"


def _load_skill_content() -> str:
    """Loads the Skill's instructions + glossary + tone templates. Called
    only from generate_explanation_node -- progressive disclosure, no other
    node pays this context cost."""
    parts = []
    for fname in ("SKILL.md", "glossary_kz_ru.md", "tone_templates.md"):
        path = SKILL_DIR / fname
        if path.exists():
            parts.append(f"--- {fname} ---\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


# --- Ingest & classification ---


def ingest_node(state: dict) -> dict:
    path = Path(state["raw_file_path"])
    file_type = "pdf" if path.suffix.lower() == ".pdf" else "image"
    content_hash = state.get("content_hash") or compute_file_hash(path.read_bytes())
    return {
        "file_type": file_type,
        "document_id": state.get("document_id") or uuid.uuid4().hex,
        "content_hash": content_hash,
    }


def classify_document_type_node(state: dict) -> dict:
    doc_type = classify_document_type(state["raw_file_path"])
    return {"document_type": doc_type}


# --- Structured (lab_panel) path ---


def ocr_extract_lab_node(state: dict) -> dict:
    result, provider = extract_lab_panel_with_fallback(state["raw_file_path"])
    return {
        "extraction": result.model_dump(),
        "extraction_confidence": result.overall_confidence,
        "confirm_attempts": state.get("confirm_attempts", 0),
    }


def validate_extraction_node(state: dict) -> dict:
    """Re-validates the (possibly user-edited) extraction dict and flags
    internal inconsistencies for the confirmation UI -- specifically the
    Day-2 finding: a value that falls outside its OWN printed reference
    range but carries no lab_flag is a strong signal of a silent misread.
    Also runs the independent (non-LLM-self-report) injection check on every
    text field, since a malicious "row" could be injected as a fake marker
    name/note rather than free narrative text."""
    extraction = LabExtraction(**state["extraction"])
    flagged_rows = []
    injection_hit = extraction.possible_injection_detected
    for v in extraction.values:
        if v.value is not None and v.lab_ref_low is not None and v.lab_ref_high is not None:
            out_of_range = not (v.lab_ref_low <= v.value <= v.lab_ref_high)
            if out_of_range and not v.lab_flag:
                flagged_rows.append(v.marker_name_as_written)
        for text_field in (v.marker_name_as_written, v.notes or "", v.value_text or ""):
            flagged, _ = check_for_injection(text_field)
            injection_hit = injection_hit or flagged
    return {
        "extraction": extraction.model_dump(),
        "_inconsistent_rows": flagged_rows,
        "_injection_detected": injection_hit,
    }


def human_confirm_node(state: dict) -> dict:
    """ALWAYS runs for the lab_panel path (unconditional -- plan Section 1/2
    Day-2 finding: model self-reported confidence was not trustworthy enough
    to gate this step). Pauses the graph via interrupt() and resumes with
    whatever the human approved/edited."""
    payload = interrupt(
        {
            "kind": "confirm_lab_extraction",
            "extraction": state["extraction"],
            "confidence": state.get("extraction_confidence"),
            "inconsistent_rows": state.get("_inconsistent_rows", []),
            "injection_detected": state.get("_injection_detected", False),
            "attempt": state.get("confirm_attempts", 0) + 1,
        }
    )
    # payload is whatever the caller passes to Command(resume=...):
    # {"approved": True, "extraction": {...possibly edited...}}
    return {
        "extraction": payload.get("extraction", state["extraction"]),
        "user_confirmed_extraction": bool(payload.get("approved")),
        "confirm_attempts": state.get("confirm_attempts", 0) + 1,
    }


def lookup_reference_ranges_node(state: dict) -> dict:
    extraction = LabExtraction(**state["extraction"])
    codes = [v.marker_code for v in extraction.values if v.marker_code]
    with Session(_engine) as session:
        ranges = _get_reference_ranges(session, codes, {"condition": "pbc_cirrhosis", "on_udca": True})
    return {"reference_ranges": {r["marker_code"]: r for r in ranges if "marker_code" in r}}


def compute_trend_node(state: dict) -> dict:
    extraction = LabExtraction(**state["extraction"])
    codes = [v.marker_code for v in extraction.values if v.marker_code]
    with Session(_engine) as session:
        trend = _compute_trend(session, state["patient_id"], codes, lookback_n_reports=5)
    return {"trend": trend}


def classify_severity_node(state: dict) -> dict:
    """Deterministic rule engine -- plan Section 2/3: severity/escalation
    decisions must be testable, never LLM-generated.

    Real-usage bug found: a ferritin reading of 748.83 against a normal
    range of 12-135 (>5x the upper bound) was classified "stable" -- this
    rule engine previously checked ONLY critical_low/critical_high (usually
    unset for a marker added via the suggest-and-approve flow, since that
    UI doesn't even expose critical-threshold fields) and trend DIRECTION
    (meaningless on a marker's first-ever reading, which reports
    "insufficient_data" and was silently treated the same as "stable" by
    the old fallback). A value simply outside its own NORMAL range -- even
    without crossing a separate, rarer "critical" cutoff, and even with no
    prior reading to compare a trend against -- must not be invisible to
    this classifier."""
    extraction = LabExtraction(**state["extraction"])
    ranges = state.get("reference_ranges", {})

    critical_hit = None
    out_of_range_markers = []
    for v in extraction.values:
        if not v.marker_code or v.value is None:
            continue
        r = ranges.get(v.marker_code)
        if not r:
            continue
        if r.get("critical_low") is not None and v.value <= r["critical_low"]:
            critical_hit = (v.marker_code, "below_critical_low")
            break
        if r.get("critical_high") is not None and v.value >= r["critical_high"]:
            critical_hit = (v.marker_code, "above_critical_high")
            break
        if r.get("normal_low") is not None and v.value < r["normal_low"]:
            out_of_range_markers.append(v.marker_code)
        elif r.get("normal_high") is not None and v.value > r["normal_high"]:
            out_of_range_markers.append(v.marker_code)

    if critical_hit:
        return {"severity": "critical", "escalation_level": "seek_care_now", "_critical_marker": critical_hit[0], "_critical_reason": critical_hit[1]}

    directions = [m["direction"] for m in state.get("trend", {}).get("markers", {}).values()]
    if "worsening" in directions or out_of_range_markers:
        return {"severity": "worsening", "escalation_level": "see_doctor_soon", "_out_of_range_markers": out_of_range_markers}
    if directions and all(d in ("improving", "stable") for d in directions):
        return {"severity": "improving" if "improving" in directions else "stable", "escalation_level": "routine"}
    return {"severity": "stable", "escalation_level": "routine"}


# --- Tone-branch nodes (plan Section 1: kept as distinct graph nodes, not
# folded into classify_severity_node, so the branching is structurally
# visible in the graph/LangSmith trace, not just a hidden state field) ---


def escalate_node(state: dict) -> dict:
    return {"_tone": "escalate"}


def decline_recommendation_node(state: dict) -> dict:
    return {"_tone": "decline"}


def encouragement_node(state: dict) -> dict:
    return {"_tone": "encourage"}


# --- RAG (shared by lab explanation and, later, followup_chat) ---


def rag_retrieve_node(state: dict) -> dict:
    severity = state.get("severity", "stable")
    query_map = {
        "critical": "urgent escalation critical lab values cirrhosis PBC what to do",
        "worsening": "worsening liver panel cirrhosis PBC lifestyle recommendations diet sleep exercise",
        "improving": "improving liver panel cirrhosis PBC encouragement",
        "stable": "stable liver panel cirrhosis PBC monitoring",
    }
    query = query_map.get(severity, query_map["stable"])
    retry_count = state.get("rag_retry_count", 0)
    result = _search_knowledge(query=query, collection="clinical_guidelines", top_k=4)
    results = result.get("results", [])

    low_relevance = (not results) or all((r.get("similarity_score") or 0) < 0.3 for r in results)
    if low_relevance and retry_count < 2:
        return {"rag_context": results, "rag_retry_count": retry_count + 1}
    return {"rag_context": results, "rag_retry_count": retry_count}


# --- Explanation generation ---


def generate_explanation_node(state: dict) -> dict:
    extraction = LabExtraction(**state["extraction"])
    ranges = state.get("reference_ranges", {})
    # Reference ranges included alongside values -- real-usage bug found: this
    # prompt previously gave the LLM bare numbers with NO normal-range
    # context at all, so it had no way to independently notice an abnormal
    # value and simply trusted the (at the time, buggy) upstream severity
    # label -- a ferritin of 748.83 against a normal range of 12-135 got
    # written up as "тұрақты" (stable). Now grounded in the actual range so
    # the explanation is checkable, not just a label-following narrative.
    values_summary_lines = []
    for v in extraction.values:
        shown_value = v.value if v.value is not None else v.value_text
        r = ranges.get(v.marker_code) if v.marker_code else None
        range_note = ""
        if r and r.get("normal_low") is not None and r.get("normal_high") is not None:
            range_note = f" (норма/normal: {r['normal_low']}-{r['normal_high']})"
        values_summary_lines.append(f"- {v.marker_name_as_written} ({v.marker_code}): {shown_value} {v.unit or ''}{range_note}")
    values_summary = "\n".join(values_summary_lines)

    out_of_range = state.get("_out_of_range_markers") or []
    out_of_range_note = (
        f"\nMarkers outside their normal range (must be explicitly mentioned, this is why severity is not 'stable'): {', '.join(out_of_range)}"
        if out_of_range
        else ""
    )

    rag_text = "\n\n".join(f"[{r.get('source_title')}] {r.get('chunk_text')}" for r in state.get("rag_context", []))
    severity = state.get("severity", "stable")
    escalation = state.get("escalation_level", "routine")
    skill_content = _load_skill_content()

    prompt = f"""{skill_content}

---

Apply the skill above to this specific case.

Extracted values (with normal reference ranges where known):
{values_summary}
{out_of_range_note}

Severity assessment (computed deterministically upstream -- use the matching template, do not re-derive): {severity}
Escalation level: {escalation}

Relevant clinical context (retrieved from clinical_guidelines, cite loosely, don't dump verbatim):
{rag_text}

Write TWO complete versions of the explanation, KAZAKH FIRST then Russian
(Kazakh is this app's primary language -- feedback from real use: "Маған ең
бірінші керек тіл ол қазақша"), following the skill's structure exactly.

IMPORTANT -- plain language (feedback from real use: the first version was
too clinical/full of medical jargon): write as if explaining to a family
member with no medical background. Prefer everyday words over clinical
terms where possible (e.g. "қан ұю көрсеткіштері" over a list of acronyms).
When a clinical term is genuinely necessary, use it but briefly say what it
means in the same sentence -- don't assume the reader already knows.

Respond in this exact format:
KZ: <kazakh explanation>
RU: <russian explanation>"""

    client = get_traced_anthropic_client()
    resp = client.messages.create(
        # 2000 was too low: found via real-usage testing that two full
        # bilingual explanations (especially after the "explain terms
        # plainly" instruction made them longer) can hit max_tokens with
        # Cyrillic text mid-generation -- e.g. one real response completed
        # a full, good KZ section but got cut off partway through RU,
        # leaving explanation_ru truncated. Cyrillic burns tokens faster
        # than English per character, so this needs real headroom.
        # Raised again 4000->6000: after adding the RAG reranker (wider
        # candidate pool -> more context in rag_text), a real query in the
        # chat path (same pattern, see chat/followup_chat.py) hit
        # stop_reason=="max_tokens" with ZERO output text because Claude
        # Sonnet 5 spent the whole budget on internal "thinking" tokens
        # before any visible text -- same risk applies here since this node
        # also consumes reranked RAG context.
        model=CLAUDE_MODEL, max_tokens=6000, messages=[{"role": "user", "content": prompt}]
    )
    text = "".join(b.text for b in resp.content if b.type == "text")

    ru, kz = "", ""
    if "RU:" in text and "KZ:" in text:
        kz = text.split("KZ:")[1].split("RU:")[0].strip()
        ru = text.split("RU:")[1].strip()
    else:
        kz = text

    if resp.stop_reason == "max_tokens":
        # Still truncated even at 4000 -- surface this rather than silently
        # shipping a sentence that stops mid-word.
        note_kz = "\n\n(Ескерту: жауап толық аяқталмауы мүмкін.)"
        note_ru = "\n\n(Примечание: ответ мог быть обрезан.)"
        kz += note_kz
        ru += note_ru

    return {"explanation_ru": ru, "explanation_kz": kz}


def disclaimer_check_node(state: dict) -> dict:
    ru = state.get("explanation_ru", "")
    kz = state.get("explanation_kz", "")
    if DISCLAIMER_MARKER_RU not in ru.lower():
        ru = ru + "\n\n" + DISCLAIMER_RU
    if DISCLAIMER_MARKER_KZ not in kz.lower():
        kz = kz + "\n\n" + DISCLAIMER_KZ
    return {"explanation_ru": ru, "explanation_kz": kz, "disclaimer_present": True}


def escalate_unreadable_node(state: dict) -> dict:
    """Terminal node when confirm_attempts is exhausted -- ask for a clearer
    photo rather than looping forever or proceeding on unreliable data."""
    return {
        "explanation_ru": "Извините, не удалось надёжно распознать этот документ. Пожалуйста, попробуйте загрузить более чёткое фото.",
        "explanation_kz": "Кешіріңіз, бұл құжатты сенімді түрде тани алмадық. Анығырақ фото жүктеп көріңіз.",
    }


def save_confirm_node(state: dict) -> dict:
    """Only signals kind -- the Streamlit UI renders the full result (severity,
    both languages, MELD chart, glossary cards) from the graph's own returned
    state rather than from a separate truncated preview in the interrupt
    payload, per feedback: showing a second, Russian-only, truncated summary
    screen before the real result was confusing and redundant."""
    payload = interrupt({"kind": "confirm_save"})
    return {"user_confirmed_save": bool(payload.get("approved"))}


def persist_node(state: dict) -> dict:
    extraction = LabExtraction(**state["extraction"])
    with Session(_engine) as session:
        doc = Document(
            id=state["document_id"],
            patient_id=state["patient_id"],
            document_type="lab_panel",
            document_date=extraction.document_date,
            source_filename=Path(state["raw_file_path"]).name,
            raw_file_path=state["raw_file_path"],
            content_hash=state.get("content_hash"),
            ocr_confidence=state.get("extraction_confidence"),
            extraction_status="confirmed",
        )
        session.add(doc)

        for v in extraction.values:
            session.add(
                LabValueRow(
                    id=uuid.uuid4().hex,
                    document_id=doc.id,
                    marker_code=v.marker_code,
                    marker_name_as_written=v.marker_name_as_written,
                    value_numeric=v.value,
                    value_text=v.value_text,
                    unit=v.unit,
                    lab_reported_ref_low=v.lab_ref_low,
                    lab_reported_ref_high=v.lab_ref_high,
                    lab_flag=v.lab_flag,
                    extracted_confidence=state.get("extraction_confidence"),
                    user_confirmed=bool(state.get("user_confirmed_extraction")),
                )
            )

        assessment_id = uuid.uuid4().hex
        session.add(
            Assessment(
                id=assessment_id,
                document_id=doc.id,
                meld_na_score=(state.get("trend", {}).get("meld_na_series") or [{}])[-1].get("meld_na"),
                overall_status=state.get("severity"),
                escalation_level=state.get("escalation_level"),
                explanation_ru=state.get("explanation_ru"),
                explanation_kz=state.get("explanation_kz"),
            )
        )

        if state.get("severity") == "critical":
            session.add(
                EscalationLogEntry(
                    id=uuid.uuid4().hex,
                    assessment_id=assessment_id,
                    marker_code=state.get("_critical_marker"),
                    trigger_reason=state.get("_critical_reason", "critical_threshold"),
                    escalation_level=state.get("escalation_level", "seek_care_now"),
                )
            )

        session.commit()
    return {"assessment_id": assessment_id}


# --- Narrative path ---


def ocr_extract_narrative_node(state: dict) -> dict:
    result = extract_narrative(state["raw_file_path"])
    return {
        "narrative_text": result.text,
        "document_kind": result.document_kind,
        "document_date": result.document_date,
    }


def pii_scrub_node(state: dict) -> dict:
    result = scrub(state["narrative_text"])
    injection_flagged, patterns = check_for_injection(result.text)
    return {
        "narrative_text": result.text,
        "_injection_detected": injection_flagged,
        "_injection_patterns": patterns,
    }


def ingest_patient_history_node(state: dict) -> dict:
    n_chunks = ingest_patient_document(
        patient_id=state["patient_id"],
        document_id=state["document_id"],
        scrubbed_text=state["narrative_text"],
        document_date=state.get("document_date"),
        document_kind=state.get("document_kind"),
    )
    with Session(_engine) as session:
        session.add(
            Document(
                id=state["document_id"],
                patient_id=state["patient_id"],
                document_type="narrative",
                document_kind=state.get("document_kind"),
                document_date=state.get("document_date"),
                source_filename=Path(state["raw_file_path"]).name,
                raw_file_path=state["raw_file_path"],
                content_hash=state.get("content_hash"),
                extraction_status="confirmed",
            )
        )
        session.commit()
    return {"_patient_history_chunks_added": n_chunks}
