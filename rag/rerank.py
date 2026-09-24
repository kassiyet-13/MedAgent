"""
LLM-based reranker (plan Section 5/9 reranker item -- user explicitly asked
not to drop this: "уақыт болса reranker ді қосайық. сен оны ұмытпа").

Originally pencilled in as Cohere Rerank multilingual-v3.0 (plan Section 0),
but no COHERE_API_KEY is configured and onboarding a third vendor this close
to the deadline isn't worth it when the app already has a fast, cheap, strong
multilingual model on hand: Claude Haiku.

This stopped being a "nice to have" and became a real bug fix during actual
use: the query "2023 ж выпискада қандай емдер тағайындалған?" (what
treatments were prescribed in the 2023 discharge summary) failed to surface
the one relevant chunk out of 33 in that document -- plain embedding
similarity ranked it 13th, well outside search_knowledge's top_k=4. Confirmed
via direct Chroma query during debugging. Embedding similarity alone wasn't
good enough here, especially cross-lingual (KZ query against RU-language
medical records) and for a chunk that's mostly drug names/dosages rather than
prose matching the query's wording.

Two-stage retrieve-then-rerank: search_knowledge pulls a wider
embedding-similarity candidate pool first (cheap, fast), then this reranks
just that smaller set (~20 short passages, one LLM call) down to top_k.
"""
from __future__ import annotations

from llm_clients import get_traced_anthropic_client

RERANK_MODEL = "claude-haiku-4-5-20251001"


def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """candidates: dicts each with a "chunk_text" key. Returns top_k of them,
    reordered by relevance to query (most relevant first). Falls back to the
    original (embedding-similarity) order for anything that goes wrong --
    reranking failure should degrade to the previous behavior, not break
    retrieval entirely."""
    if len(candidates) <= top_k:
        return candidates

    numbered = "\n\n".join(f"[{i}] {c['chunk_text'][:500]}" for i, c in enumerate(candidates))
    prompt = f"""You are ranking passages by relevance to a search query for a medical
record-retrieval system. The query may be in Kazakh or Russian; passages are typically in
Russian (Kazakhstani medical records/guidelines). Judge relevance by MEANING, not shared
words -- query and passage are often in different languages.

Query: {query}

Passages:
{numbered}

Return the indices of the {top_k} most relevant passages, most relevant first."""

    try:
        client = get_traced_anthropic_client()
        resp = client.messages.create(
            model=RERANK_MODEL,
            max_tokens=200,
            tools=[
                {
                    "name": "rank_passages",
                    "description": "Record the ranked passage indices.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "ranked_indices": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": f"Exactly {top_k} indices, most relevant first.",
                            }
                        },
                        "required": ["ranked_indices"],
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "rank_passages"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if block.type == "tool_use":
                indices = block.input.get("ranked_indices", [])
                picked = [candidates[i] for i in indices if 0 <= i < len(candidates)]
                if picked:
                    return picked[:top_k]
    except Exception:
        pass
    return candidates[:top_k]
