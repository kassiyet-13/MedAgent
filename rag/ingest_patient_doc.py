"""
Ingests ONE scrubbed narrative document into the `patient_history` Chroma
collection. Called from ingest_patient_history_node in the graph (Day 3/4);
also runnable standalone for testing/backfilling real documents.

Unlike build_index.py, this is INCREMENTAL (add, not rebuild) -- the
patient_history collection is designed to grow over time as more documents
are uploaded (plan Section 5b), including with an initially partial/
incomplete document set.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import chromadb
from dotenv import load_dotenv

load_dotenv()

from rag.chunking import chunk_patient_narrative
from rag.embedding import get_embedding_function

ROOT = Path(__file__).resolve().parent.parent
CHROMA_PATH = Path(os.environ.get("MEDAGENT_CHROMA_PATH", ROOT / "data" / "chroma"))
COLLECTION_NAME = "patient_history"


def get_or_create_patient_history_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=get_embedding_function())


def ingest_patient_document(
    patient_id: str,
    document_id: str,
    scrubbed_text: str,
    document_date: str | None,
    document_kind: str | None,
) -> int:
    """Chunk + embed one already-PII-scrubbed narrative document. Returns
    the number of chunks added. Caller (pii_scrub_node) is responsible for
    scrubbing BEFORE this is called -- this function does not scrub."""
    collection = get_or_create_patient_history_collection()
    chunks = chunk_patient_narrative(scrubbed_text)

    if not chunks:
        return 0

    ids = [f"{document_id}__{i}__{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
    metadatas = [
        {
            "patient_id": patient_id,
            "document_id": document_id,
            "document_date": document_date or "",
            "document_kind": document_kind or "",
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    collection.add(ids=ids, documents=chunks, metadatas=metadatas)
    return len(chunks)


if __name__ == "__main__":
    # Manual backfill of the 3 already-scrubbed real narrative documents from
    # Day 2, so patient_history has real content to test retrieval against
    # today instead of starting completely empty.
    import re

    REVIEW_DIR = ROOT / "data" / "extraction_review"
    seeds = [
        ("vipiska1_SCRUBBED.md", "discharge_summary", "2023-05-11"),
        ("узи_extracted_SCRUBBED.md", "ultrasound_report", "2024-12-13"),
        ("fibroscan_extracted_SCRUBBED.md", "fibroscan_report", "2024-12-11"),
    ]
    total = 0
    for fname, kind, date in seeds:
        path = REVIEW_DIR / fname
        if not path.exists():
            print(f"skip (not found): {fname}")
            continue
        raw = path.read_text(encoding="utf-8")
        # Strip the markdown metadata header this repo's review files have,
        # keep only the "## Extracted text" body.
        match = re.search(r"## Extracted text\s*\n\n(.*)", raw, re.DOTALL)
        body = match.group(1) if match else raw
        n = ingest_patient_document(
            patient_id="patient_default",
            document_id=path.stem,
            scrubbed_text=body,
            document_date=date,
            document_kind=kind,
        )
        print(f"Ingested {n} chunks from {fname}")
        total += n
    print(f"Total chunks in patient_history seed: {total}")
