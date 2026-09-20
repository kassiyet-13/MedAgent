"""
Chunking strategies for the two RAG collections (plan Section 5).

clinical_guidelines: header-aware split first (keeps a full recommendation
unit like "managing ascites" intact instead of cutting mid-explanation),
then size-bounded at 600 tokens / 100-token overlap.

patient_history: simpler fixed-size chunking (~400 tokens) since narrative
documents (discharge summaries, imaging reports) are shorter and less
uniformly structured than the sourced clinical guidelines.
"""
from __future__ import annotations

import tiktoken
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _token_len(text: str) -> int:
    return len(_ENCODING.encode(text))


def chunk_clinical_markdown(text: str, source_title: str) -> list[dict]:
    """Returns a list of {"text": ..., "section": ...} dicts."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2")], strip_headers=False
    )
    header_docs = header_splitter.split_text(text)

    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600, chunk_overlap=100, length_function=_token_len
    )

    chunks: list[dict] = []
    for doc in header_docs:
        section = doc.metadata.get("h2") or doc.metadata.get("h1") or source_title
        for piece in size_splitter.split_text(doc.page_content):
            chunks.append({"text": piece, "section": section})
    return chunks


def chunk_patient_narrative(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400, chunk_overlap=60, length_function=_token_len
    )
    return splitter.split_text(text)
