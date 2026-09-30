"""graph/nodes.py::rag_retrieve_node -- each retry must use a DIFFERENT,
broader query, and a worse retry must not replace a better earlier result.
Search is stubbed, so no API calls."""
import graph.nodes as nodes
from graph.edges import MAX_RAG_RETRIES, route_after_rag


def _run_loop(monkeypatch, scores_by_attempt):
    queries = []

    def fake_search(query, collection, top_k):
        attempt = len(queries)
        queries.append(query)
        return {"results": [{"chunk_text": f"a{attempt}", "similarity_score": scores_by_attempt[attempt]}]}

    monkeypatch.setattr(nodes, "_search_knowledge", fake_search)
    state = {
        "severity": "worsening",
        "_out_of_range_markers": ["ALP", "GGT"],
        "reference_ranges": {"ALP": {"marker_name_en": "Alkaline phosphatase"}, "GGT": {"marker_name_en": "GGT"}},
    }
    state.update(nodes.rag_retrieve_node(state))
    while route_after_rag(state) == "rag_retrieve_node":
        state.update(nodes.rag_retrieve_node(state))
    return queries, state


def test_retries_broaden_the_query(monkeypatch):
    queries, state = _run_loop(monkeypatch, [0.1, 0.1, 0.1])
    assert len(queries) == 1 + MAX_RAG_RETRIES
    assert len(set(queries)) == len(queries)  # never the same query twice
    assert "Alkaline phosphatase" in queries[0] and "GGT" in queries[0]
    assert "Alkaline phosphatase" not in queries[1]
    assert queries[2] == nodes.RAG_BROADEST_QUERY


def test_worse_retry_keeps_better_earlier_result(monkeypatch):
    _, state = _run_loop(monkeypatch, [0.25, 0.05, 0.02])
    assert state["rag_context"][0]["chunk_text"] == "a0"


def test_no_retry_when_first_search_is_relevant(monkeypatch):
    queries, state = _run_loop(monkeypatch, [0.7])
    assert len(queries) == 1
    assert state["rag_attempts"] == 1
