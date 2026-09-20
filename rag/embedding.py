"""
Shared embedding function -- MUST be used identically by every place that
creates OR queries a Chroma collection (build_index.py, ingest_patient_doc.py,
mcp_server/tools/knowledge_search.py). Chroma does not remember which
embedding function a collection was built with; if a query used a different
one (e.g. Chroma's local default instead of this OpenAI one), similarity
search would silently compare vectors from two different embedding spaces
and return garbage. Centralizing this one factory function is what prevents
that class of bug.
"""
from __future__ import annotations

import os

from chromadb.utils import embedding_functions

EMBEDDING_MODEL = "text-embedding-3-small"


def get_embedding_function():
    api_key = os.environ["OPENAI_API_KEY"]
    return embedding_functions.OpenAIEmbeddingFunction(api_key=api_key, model_name=EMBEDDING_MODEL)
