"""
MedAgent's own MCP server (stdio transport), exposing 3 tools.

Run directly for manual testing:      python -m mcp_server.server
Inspect with the official MCP inspector:  mcp dev mcp_server/server.py

Why this is an MCP server and not just plain Python functions called
in-process (the "why MCP" defense answer, plan Section 3):
1. Typed, protocol-level tool schemas usable by ANY MCP client (Claude
   Desktop, a future clinician-facing tool, this app's own LangGraph nodes)
   without touching this codebase.
2. Each tool call is a separately traceable step, visible in the MCP
   inspector standalone and in LangSmith once wired into the graph.
3. Tools are independently unit-testable and swappable (e.g. the Chroma
   backend behind search_knowledge could become Qdrant without any client
   code changing).
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from sqlalchemy.orm import Session

from data.seed_db import get_engine
from mcp_server.tools.knowledge_search import search_knowledge as _search_knowledge
from mcp_server.tools.reference_ranges import get_reference_ranges as _get_reference_ranges
from mcp_server.tools.trend import compute_trend as _compute_trend

# NOTE: mcp SDK v2 renamed FastMCP -> MCPServer (same .tool()/.run() interface
# we rely on here); see https://py.sdk.modelcontextprotocol.io/v2/migration/
mcp = MCPServer("medagent")
_engine = get_engine()


@mcp.tool()
def get_reference_ranges(markers: list[str], patient_context: dict | None = None) -> list[dict]:
    """
    Look up normal/critical reference ranges for liver-panel and PBC-specific
    lab markers, with cirrhosis/PBC-aware notes (e.g. UDCA biochemical-response
    thresholds). markers: list of marker codes like ["ALT", "PLATELETS", "AMA_M2"].
    patient_context: optional dict, e.g. {"condition": "pbc_cirrhosis", "on_udca": true}.
    """
    with Session(_engine) as session:
        return _get_reference_ranges(session, markers, patient_context)


@mcp.tool()
def compute_trend(patient_id: str, marker_codes: list[str], lookback_n_reports: int = 5) -> dict:
    """
    Compute per-marker value history and direction (improving/worsening/stable)
    across a patient's past lab reports, plus a MELD-Na score series wherever
    bilirubin, INR, creatinine, and sodium are all available for the same date.
    Pure deterministic SQL + arithmetic -- never LLM-generated.
    """
    with Session(_engine) as session:
        return _compute_trend(session, patient_id, marker_codes, lookback_n_reports)


@mcp.tool()
def search_knowledge(query: str, collection: str, top_k: int = 4, marker_filter: str | None = None) -> dict:
    """
    Search one of two knowledge collections: "clinical_guidelines" (sourced
    medical reference corpus) or "patient_history" (this patient's own
    ingested documents, PII-scrubbed). Returns ranked text chunks with source
    attribution. Backed by Chroma; built by rag/build_index.py (clinical) and
    rag/ingest_patient_doc.py (patient history) on Day 3.
    """
    return _search_knowledge(query, collection, top_k, marker_filter)


if __name__ == "__main__":
    mcp.run()
