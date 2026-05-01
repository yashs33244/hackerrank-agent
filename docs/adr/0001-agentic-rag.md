# ADR-0001: Agentic RAG over Standard RAG

**Status:** Accepted  
**Date:** 2026-05-01

## Context

The pipeline must retrieve relevant corpus excerpts to ground its responses. Two retrieval strategies were considered:

**Option A — Standard RAG:** Embed the ticket, retrieve top-k chunks, pass directly to the LLM responder.

**Option B — Agentic RAG:** The ResponderAgent calls a `search_corpus()` tool; the LLM decides the query and can iteratively refine it.

## Decision

Agentic RAG (Option B) was selected.

## Rationale

- Standard RAG uses the raw ticket text as the embedding query. For multi-domain tickets or ambiguous phrasing, this produces poor retrieval.
- Agentic RAG allows the responder to reformulate the query based on the classified intent and domain — producing more targeted retrieval.
- The agent can issue a domain-scoped query first, then fall back to an unscoped query if no results are found.
- The tool-call interface makes retrieval auditable: the CriticAgent can trace each claim to a specific chunk with a source header.
- The added latency (~1 extra LLM call) is acceptable given the quality improvement and evaluation criteria that reward grounded responses.

## Consequences

- **Positive:** Higher grounding scores from CriticAgent. Better handling of cross-domain ambiguity.
- **Negative:** One additional LLM call per ticket. Mitigated by using a medium-load model for the responder.
- **Risk:** If the LLM reformulates the query poorly, retrieval degrades. Mitigated by domain scoping from RouterAgent.
