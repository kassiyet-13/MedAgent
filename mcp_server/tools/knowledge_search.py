"""
Tool 3: search_knowledge

Plan Section 3: one parameterized tool searching either of the two Chroma
collections (clinical_guidelines / patient_history) rather than a fourth
tool -- keeps the MCP surface at 3 substantive tools while serving both
rag_retrieve_node and followup_chat.

STUB STATUS (Day 2): the Chroma collections don't exist yet -- they're built
in rag/build_index.py and rag/ingest_patient_doc.py on Day 3. Until then this
returns a clearly-labeled stub response instead of crashing, so the MCP
server itself can be stood up and tested end-to-end now.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent.parent
CHROMA_PATH = Path(os.environ.get("MEDAGENT_CHROMA_PATH", ROOT / "data" / "chroma"))

Collection = Literal["clinical_guidelines", "patient_history"]
VALID_COLLECTIONS = {"clinical_guidelines", "patient_history"}


def search_knowledge(query: str, collection: Collection, top_k: int = 4, marker_filter: str | None = None) -> dict:
    if collection not in VALID_COLLECTIONS:
        return {"error": f"invalid collection '{collection}', must be one of {sorted(VALID_COLLECTIONS)}"}

    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        existing = {c.name for c in client.list_collections()}
        if collection not in existing:
            return {
                "stub": True,
                "reason": f"Collection '{collection}' not built yet -- run rag/build_index.py "
                "(clinical_guidelines) or rag/ingest_patient_doc.py (patient_history) first (Day 3).",
                "query": query,
                "results": [],
            }

        coll = client.get_collection(collection)
        where = {"marker_code": marker_filter} if marker_filter else None
        res = coll.query(query_texts=[query], n_results=top_k, where=where)

        results = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            results.append(
                {
                    "chunk_text": doc,
                    "source_title": (meta or {}).get("source_title"),
                    "source_url": (meta or {}).get("source_url"),
                    "section": (meta or {}).get("section"),
                    "similarity_score": 1 - dist if dist is not None else None,
                }
            )
        return {"stub": False, "query": query, "results": results}

    except ImportError:
        return {"error": "chromadb not installed"}
