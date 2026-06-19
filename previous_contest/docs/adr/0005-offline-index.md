# ADR-0005: Pre-Built Offline Index Strategy

**Status:** Accepted  
**Date:** 2026-05-01

## Context

The retrieval pipeline requires a BM25 index and chunk embeddings. These can be built:

**Option A — At startup:** Index built fresh each time `main.py` runs.  
**Option B — Pre-built and committed:** Index artifacts (`chunks.jsonl`, `embeddings.npy`, `bm25_corpus.txt`) built once and checked into the repository.

## Decision

Pre-built offline index (Option B).

## Rationale

- The corpus is static for the duration of the hackathon. Rebuilding at startup is wasted work on every run.
- Startup time is a factor in automated evaluation environments — a pre-built index enables instant startup.
- Committing the index ensures **reproducibility**: any evaluator running the submission gets identical retrieval behaviour.
- Embedding API calls are expensive and slow. A pre-built index eliminates this cost at query time entirely.
- The `build.py` script is retained so the index can be rebuilt if the corpus changes.

## Consequences

- **Positive:** Instant startup. Consistent, reproducible retrieval across runs and machines.
- **Positive:** No embedding API calls at query time.
- **Negative:** Index artifacts add ~5–10 MB to the repository.
- **Risk:** Index becomes stale if the corpus is updated without rebuilding. Mitigated by `build.py` and the clear `docs/` documentation.
