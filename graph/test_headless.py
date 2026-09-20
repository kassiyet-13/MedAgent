"""
Day 3 milestone script (plan Section 13/Verification): headless end-to-end
run through the graph for both a narrative document and a lab-panel image,
including the HITL interrupt/resume mechanic on the lab path. Not part of
the final app -- a manual verification script.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from graph.build_graph import build_graph, CHECKPOINT_DB

ROOT = Path(__file__).resolve().parent.parent


def run_narrative_test(graph):
    print("\n" + "=" * 70)
    print("NARRATIVE PATH TEST: узи.jpeg")
    print("=" * 70)
    config = {"configurable": {"thread_id": f"test-narrative-{uuid.uuid4().hex[:8]}"}}
    result = graph.invoke(
        {
            "patient_id": "patient_default",
            "raw_file_path": str(ROOT / "data" / "sample_documents" / "узи.jpeg"),
        },
        config=config,
    )
    print("document_type:", result.get("document_type"))
    print("document_kind:", result.get("document_kind"))
    print("narrative_text length:", len(result.get("narrative_text", "")))
    print("chunks added to patient_history:", result.get("_patient_history_chunks_added"))


def run_lab_test_with_hitl(graph):
    print("\n" + "=" * 70)
    print("LAB PATH TEST: lab_2024_12.jpeg (with HITL pause/resume)")
    print("=" * 70)
    config = {"configurable": {"thread_id": f"test-lab-{uuid.uuid4().hex[:8]}"}}

    result = graph.invoke(
        {
            "patient_id": "patient_default",
            "raw_file_path": str(ROOT / "data" / "sample_documents" / "lab_2024_12.jpeg"),
        },
        config=config,
    )

    if "__interrupt__" in result:
        interrupt_payload = result["__interrupt__"][0].value
        print("PAUSED at human_confirm_node. Payload kind:", interrupt_payload["kind"])
        print("Extracted values count:", len(interrupt_payload["extraction"]["values"]))
        print("Inconsistent rows flagged:", interrupt_payload["inconsistent_rows"])
        print("-> Simulating user clicking 'Approve' with no edits...")

        result = graph.invoke(
            Command(resume={"approved": True, "extraction": interrupt_payload["extraction"]}), config=config
        )

    if "__interrupt__" in result:
        interrupt_payload = result["__interrupt__"][0].value
        print("PAUSED at:", interrupt_payload["kind"])
        print("-> Simulating user clicking 'Save'...")
        result = graph.invoke(Command(resume={"approved": True}), config=config)

    print("\nFinal severity:", result.get("severity"))
    print("Escalation level:", result.get("escalation_level"))
    print("MELD-Na series:", result.get("trend", {}).get("meld_na_series"))
    print("\n--- Explanation (RU) ---")
    print(result.get("explanation_ru", "")[:500])
    print("\n--- Explanation (KZ) ---")
    print(result.get("explanation_kz", "")[:500])
    print("\nAssessment ID:", result.get("assessment_id"))


if __name__ == "__main__":
    with SqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        run_narrative_test(graph)
        run_lab_test_with_hitl(graph)
