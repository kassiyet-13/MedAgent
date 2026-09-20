"""
Builds the `clinical_guidelines` Chroma collection from rag/corpus/clinical/*.md.

Run: python -m rag.build_index
Idempotent: deletes and rebuilds the collection each run (small corpus,
cheap to redo -- avoids drift between the source .md files and the index).
"""
from __future__ import annotations

import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv

load_dotenv()

from rag.chunking import chunk_clinical_markdown
from rag.embedding import get_embedding_function

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "rag" / "corpus" / "clinical"
CHROMA_PATH = Path(os.environ.get("MEDAGENT_CHROMA_PATH", ROOT / "data" / "chroma"))
COLLECTION_NAME = "clinical_guidelines"


def _extract_title(md_text: str, fallback: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def main():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    existing = {c.name for c in client.list_collections()}
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(name=COLLECTION_NAME, embedding_function=get_embedding_function())

    md_files = sorted(CORPUS_DIR.glob("*.md"))
    md_files = [f for f in md_files if f.name != "SOURCES.md"]

    all_ids, all_docs, all_metas = [], [], []
    for f in md_files:
        text = f.read_text(encoding="utf-8")
        title = _extract_title(text, fallback=f.stem)
        chunks = chunk_clinical_markdown(text, source_title=title)
        for i, chunk in enumerate(chunks):
            all_ids.append(f"{f.stem}__{i}")
            all_docs.append(chunk["text"])
            all_metas.append({"source_title": title, "source_file": f.name, "section": chunk["section"]})

    if not all_docs:
        print("No corpus documents found -- nothing indexed.")
        return

    collection.add(ids=all_ids, documents=all_docs, metadatas=all_metas)
    print(f"Indexed {len(all_docs)} chunks from {len(md_files)} files into '{COLLECTION_NAME}' at {CHROMA_PATH}")


if __name__ == "__main__":
    main()
