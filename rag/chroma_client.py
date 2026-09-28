"""
One Chroma client per process.

Every search used to construct its own chromadb.PersistentClient. Created
from several threads at once (the multi-analysis upload, parallel eval
workers), those clients race inside chromadb's shared per-path system cache
and fail with KeyError('data\\chroma') / "'RustBindingsAPI' object has no
attribute 'bindings'". Found when the history chat started reading whole
documents (more Chroma calls per question) and the eval ran 2 workers.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent
CHROMA_PATH = Path(os.environ.get("MEDAGENT_CHROMA_PATH", ROOT / "data" / "chroma"))

_client = None
_lock = threading.Lock()


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    with _lock:
        if _client is None:
            _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        return _client
