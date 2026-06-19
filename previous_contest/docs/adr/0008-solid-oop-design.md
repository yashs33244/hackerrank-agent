# ADR-0008: SOLID OOP Design with Protocol-Based Dependency Injection

**Status:** Accepted  
**Date:** 2026-05-01

## Context

As the codebase grew from a single script to a five-agent pipeline, several design choices became necessary:

- How should agents share common behaviour (prompt loading, LLM calls, JSON parsing)?
- How should the Gemini client be provisioned — tightly coupled or injected?
- How should the retrieval and compression components be swappable for testing?

## Decision

Abstract base class (`AbstractAgent`) + Protocol-based dependency injection.

**Key decisions:**
1. `AbstractAgent` provides shared behaviour via the Template Method pattern. Each agent subclass implements only `run()`.
2. `LLMClient`, `Searcher`, and `ContextCompressor` are defined as `Protocol` types in `domain/types.py`. Agents depend on these protocols, not on concrete implementations.
3. `PipelineFactory` is the single composition root — all dependency wiring happens there.
4. `GeminiClientFactory` uses the Flyweight pattern — one client instance per cognitive-load tier, shared across agents.
5. All enums and domain constants live in `domain/enums.py`. No string literals for constrained values outside this module.

## Rationale

**AbstractAgent:**
- Eliminates code duplication (prompt loading, `_call_llm`, `_parse_json`, `_extract_response_text` are identical across agents).
- New agents are added by subclassing — no modification to existing code (Open/Closed principle).

**Protocol-based DI:**
- `BM25Searcher` can be swapped for a vector-DB searcher without changing `ResponderAgent`.
- `LLMContextCompressor` can be replaced by a non-LLM compressor for testing.
- Makes unit testing straightforward — inject a mock client that returns fixed JSON.

**PipelineFactory:**
- All dependency wiring in one place. Changing a model or switching an implementation touches only the factory.
- Follows the Dependency Inversion principle at the system level.

**Enums in `domain/enums.py`:**
- Prevents scattered string literals (`"replied"`, `"escalated"`) from drifting out of sync.
- IDE auto-complete and type checking catch invalid values at development time.

## Consequences

- **Positive:** Easy to test individual agents in isolation with mock clients.
- **Positive:** Easy to swap any component (retriever, compressor, model) without touching agent logic.
- **Negative:** Slightly more files and imports than a monolithic script.
- **Risk:** Protocol matching in Python is structural (duck typing), not enforced at runtime. Mitigated by mypy type checking.
