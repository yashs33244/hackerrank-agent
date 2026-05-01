# ADR-0006: Typed Shared State Object (TicketState)

**Status:** Accepted  
**Date:** 2026-05-01

## Context

In a multi-agent pipeline, agents need to share data. Common approaches:

**Option A — Dictionary passing:** Flexible but untyped; agents can accidentally read or overwrite each other's fields.  
**Option B — Message bus / event queue:** Decoupled but adds complexity; overkill for a linear pipeline.  
**Option C — Typed dataclass:** Single object flows through the pipeline; each agent reads/writes only its declared fields.

## Decision

Typed shared state via `TicketState` dataclass (Option C), defined in `domain/types.py`.

## Rationale

- A typed dataclass provides field-level documentation: it is immediately clear which agent owns which field.
- Type hints enable static analysis (mypy) to catch field access errors at development time, not runtime.
- The single-object approach keeps context windows scoped: each agent reads only its own fields and writes only its outputs. No agent sees another agent's full reasoning trace.
- Compared to a dictionary, a dataclass prevents typo-based key errors (`triage_reson` vs `triage_reason`).
- The dataclass is mutable — agents update fields in-place — which avoids unnecessary object copying in a sequential pipeline.

## Consequences

- **Positive:** Type safety. Self-documenting ownership model.
- **Positive:** Easy to add new fields as the pipeline evolves — just add a field with a default value.
- **Negative:** Shared mutable state is not thread-safe. This is acceptable because the pipeline is sequential, not concurrent.
- **Risk:** Agents could in principle read each other's fields. Convention (enforced by code review) prevents this.
