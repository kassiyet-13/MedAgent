"""
Tool 3: search_knowledge

Plan Section 3: one parameterized tool searching either of the two Chroma
collections (clinical_guidelines / patient_history) rather than a fourth
tool -- keeps the MCP surface at 3 substantive tools while serving both
rag_retrieve_node and followup_chat.

Day 3 update: both collections are now real (rag/build_index.py,
rag/ingest_patient_doc.py) -- the stub path below only fires if a collection
genuinely hasn't been built yet, e.g. a fresh checkout before running those
scripts.

IMPORTANT: get_collection() below passes the SAME embedding function
(rag/embedding.py) used when the collection was created. Chroma does not
remember a collection's embedding function on its own -- querying without
explicitly passing it back would silently fall back to Chroma's local
default embedder, comparing vectors from two different embedding spaces
and returning meaningless results. This was caught and fixed during Day 3
build before it could cause a silent retrieval-quality bug.
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

        from rag.embedding import get_embedding_function

        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        existing = {c.name for c in client.list_collections()}
        if collection not in existing:
            return {
                "stub": True,
                "reason": f"Collection '{collection}' not built yet -- run rag/build_index.py "
                "(clinical_guidelines) or rag/ingest_patient_doc.py (patient_history) first.",
                "query": query,
                "results": [],
            }

        coll = client.get_collection(collection, embedding_function=get_embedding_function())
        if coll.count() == 0:
            return {"stub": False, "query": query, "results": []}
        # marker_filter is accepted for forward-compatibility with a future
        # per-marker-tagged chunking pass but isn't wired to real metadata
        # yet (neither collection currently stores a marker_code field) --
        # left as a documented no-op rather than silently erroring.

        # Retrieve a wider embedding-similarity candidate pool than top_k,
        # then rerank down to top_k (rag/rerank.py). Real bug found via
        # actual use: plain embedding similarity ranked the one relevant
        # chunk 13th out of 33 in a single document for a real query -- top_k
        # alone (previously requested straight from Chroma) was nowhere near
        # enough. n_results is capped by the collection's actual size.
        candidate_pool = min(max(top_k * 5, 20), coll.count())
        res = coll.query(query_texts=[query], n_results=candidate_pool)

        candidates = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            candidates.append(
                {
                    "chunk_text": doc,
                    "source_title": (meta or {}).get("source_title"),
                    "source_url": (meta or {}).get("source_url"),
                    "section": (meta or {}).get("section"),
                    "similarity_score": 1 - dist if dist is not None else None,
                }
            )

        from rag.rerank import rerank

        results = rerank(query, candidates, top_k) if candidates else candidates
        return {"stub": False, "query": query, "results": results}

    except ImportError:
        return {"error": "chromadb not installed"}
