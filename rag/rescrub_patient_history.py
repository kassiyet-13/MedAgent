"""
Maintenance for the patient_history Chroma collection, after two findings
while building the eval golden dataset:

1. PII that got past an older version of guardrails/pii_scrub.py (a date of
   birth written without a colon) is already embedded. Re-running the
   CURRENT scrubber over every stored chunk and re-embedding the changed ones
   is the only way to get it out -- the collection doesn't keep raw text.
2. Orphan duplicates: the Day-3 manual seed (rag/ingest_patient_doc.py
   __main__) ingested three documents that were later uploaded again through
   the app. The seed copies have no row in the SQL documents table, so the
   upload dedup (which checks that table) never saw them, and retrieval
   returned the same text twice.

Dry run by default -- prints what would change. --apply writes.
Run: python -m rag.rescrub_patient_history [--apply]
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import Document
from data.seed_db import get_engine
from guardrails.pii_scrub import scrub
from rag.ingest_patient_doc import get_or_create_patient_history_collection


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    coll = get_or_create_patient_history_collection()
    res = coll.get(include=["documents", "metadatas"])
    with Session(get_engine()) as session:
        known_doc_ids = set(session.execute(select(Document.id)).scalars())

    orphan_ids, changed = [], []
    for chunk_id, text, meta in zip(res["ids"], res["documents"], res["metadatas"]):
        if meta.get("document_id") not in known_doc_ids:
            orphan_ids.append(chunk_id)
            continue
        scrubbed = scrub(text)
        if scrubbed.text != text:
            changed.append((chunk_id, scrubbed.text, scrubbed.redaction_types_found))

    orphan_docs = sorted({m.get("document_id") for m, i in zip(res["metadatas"], res["ids"]) if i in set(orphan_ids)})
    print(f"Chunks total: {len(res['ids'])}")
    print(f"Orphan chunks (no SQL document row): {len(orphan_ids)} from {orphan_docs}")
    print(f"Chunks changed by re-scrub: {len(changed)}")
    for chunk_id, _, found in changed:
        print(f"  {chunk_id[:40]}: {found}")

    if not args.apply:
        print("\nDry run -- nothing written. Re-run with --apply.")
        return
    if orphan_ids:
        coll.delete(ids=orphan_ids)
    if changed:
        coll.update(ids=[c[0] for c in changed], documents=[c[1] for c in changed])
    print(f"\nApplied: deleted {len(orphan_ids)}, re-scrubbed {len(changed)}. Remaining chunks: {coll.count()}")


if __name__ == "__main__":
    main()
