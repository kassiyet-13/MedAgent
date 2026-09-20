"""
Shared, LangSmith-traced LLM client factories.

Plan's mandatory LangSmith requirement ("each call becomes a discrete
traceable LangSmith step") needs more than just LANGSMITH_TRACING=true in
.env -- that env var makes LangGraph's own node-by-node execution show up
in LangSmith automatically, but a RAW `anthropic.Anthropic()`/`OpenAI()`
call made inside a node is invisible to LangSmith unless the client itself
is wrapped. `wrap_anthropic`/`wrap_openai` add that instrumentation (exact
prompt, completion, token counts, latency) as a nested span under the
graph's trace, without changing how the client is called anywhere else in
the code.
"""
from __future__ import annotations

import os

import anthropic
from langsmith.wrappers import wrap_anthropic


def get_traced_anthropic_client() -> anthropic.Anthropic:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    try:
        return wrap_anthropic(client)
    except AttributeError:
        # Found during Day 4 browser testing: installed langsmith==0.13.0's
        # wrap_anthropic unconditionally touches client.completions.create
        # (the legacy, pre-Messages-API surface), which anthropic==1.7.0 no
        # longer exposes at all -- an incompatibility between these two
        # library versions' release cadence, not a bug in this app's code.
        # Falling back to the plain client keeps the app working; LangGraph's
        # own node-level tracing (LANGSMITH_TRACING=true) still shows up in
        # the dashboard either way -- only the extra nested per-LLM-call span
        # (exact prompt/completion/token count) is lost in this fallback.
        return client
