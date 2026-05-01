# ADR-0003: Hybrid BM25 + Cosine Similarity Retrieval

**Status:** Accepted  
**Date:** 2026-05-01

## Context

Retrieval quality directly determines grounding quality, which determines critic pass rates. Three retrieval strategies were evaluated:

**Option A — Pure BM25:** Fast keyword matching, zero API cost, poor semantic coverage.  
**Option B — Pure semantic (dense retrieval):** Embedding-based cosine similarity, high API cost, poor for exact keyword match.  
**Option C — Hybrid:** BM25 for initial candidate filtering, cosine similarity for reranking.

## Decision

Hybrid retrieval (Option C) with a two-stage pipeline:
1. BM25 produces a candidate set of `BM25_TOP_K=20` chunks
2. Cosine similarity reranks the candidates to `FINAL_TOP_K=3`

## Rationale

- BM25 is extremely efficient — it eliminates ~95% of irrelevant chunks at zero LLM cost.
- Cosine similarity captures semantic equivalence that BM25 misses (e.g., "card blocked" ↔ "payment declined").
- The two-stage approach combines the strengths of both: fast initial filtering + semantic precision.
- Embeddings are pre-computed and stored in `embeddings.npy` — no embedding API call at query time.
- The hybrid approach is more robust to vocabulary mismatch, which is common in multi-domain support tickets.

## Consequences

- **Positive:** High retrieval precision across keyword-heavy (Visa) and semantic-heavy (Claude) ticket types.
- **Positive:** No embedding API call at query time — index is pre-built.
- **Negative:** Index must be rebuilt when the corpus changes.
- **Risk:** BM25 candidate pool (`TOP_K=20`) may not include the optimal chunk for unusual queries. Fallback to unscoped search mitigates this.
