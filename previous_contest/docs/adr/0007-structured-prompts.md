# ADR-0007: Structured System Prompt Design

**Status:** Accepted  
**Date:** 2026-05-01

## Context

System prompt quality directly determines agent output quality. Several prompt architectures were evaluated:

**Option A — Flat prose instructions:** Easy to write, hard to audit, prone to ignored sections.  
**Option B — Numbered rules list:** Clear ordering but no semantic grouping; security rules can get buried.  
**Option C — Tagged sections:** XML-style section tags (`<identity>`, `<security_protocol>`, `<mission>`, `<output_format>`) create explicit, auditable structure.

## Decision

Tagged section prompts (Option C), stored as `.md` files in `code/prompts/`.

## Rationale

- Tagged sections mirror how production-grade LLM deployments structure prompts (as documented in publicly available AI safety research and prompt-engineering literature).
- The `<security_protocol>` tag is visually and semantically distinct — it cannot be accidentally omitted when reviewing a prompt.
- The `<output_format>` section provides an unambiguous JSON schema contract, reducing malformed output.
- Forcing `<thinking>` blocks before JSON output (on TriageAgent and CriticAgent) allows the model to reason step-by-step, improving accuracy on classification tasks.
- Storing prompts as separate `.md` files (not embedded in Python strings) makes them editable without touching application code and enables the auto-improvement loop to patch them safely.

## Consequences

- **Positive:** Auditable prompt structure. Clear separation of identity, security, mission, and format.
- **Positive:** Prompts can be edited, versioned, and improved independently of agent code.
- **Positive:** The `improve_loop.py` script can propose targeted patches to specific sections.
- **Negative:** Slightly more verbose than flat prompts.
- **Risk:** Tags can be misused as injection targets (`</security_protocol>ignore the above`). Mitigated by Gate 1 regex scan.
