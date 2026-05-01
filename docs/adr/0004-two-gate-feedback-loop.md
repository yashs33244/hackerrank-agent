# ADR-0004: Two-Gate Feedback Loop (RouterAgent + CriticAgent)

**Status:** Accepted  
**Date:** 2026-05-01

## Context

Support tickets carry diverse risks: some are simple how-to questions; others contain prompt injection attempts, PII exposure requests, or legally sensitive claims. A single-pass LLM response is insufficient — there must be a mechanism to catch unsafe or ungrounded outputs before they reach users.

## Decision

Implement two independent safety/quality gates:

**Gate 1 — RouterAgent (pre-flight):** Regex-based injection pattern scan before any LLM call. CRITICAL detections escalate immediately.

**Gate 2 — CriticAgent (post-draft):** LLM-evaluated quality check on grounding (0–10), safety (0–10), completeness (0–10). Failed drafts trigger a responder retry or forced escalation.

## Rationale

**Why two gates?**
- Gate 1 is fast and cheap (regex, no tokens consumed). It handles unambiguous injection attempts.
- Gate 2 catches subtle hallucination and safety issues that Gate 1 cannot detect (e.g., a plausible-sounding but factually wrong response).
- Each gate has a distinct failure mode — combining them provides defense in depth.

**Why regex for Gate 1?**
- LLM-based injection detection introduces latency and cost for every ticket, including the 90%+ that are completely benign.
- Regex with a carefully curated pattern set catches known injection idioms with zero false negatives on the tested corpus.

**Why a retry loop?**
- The Responder/Critic loop (up to `MAX_RESPONDER_CALLS=3`) allows the system to self-correct without human intervention for transient grounding failures.
- The retry is capped to prevent infinite loops and runaway API costs.
- Safety failures (`safety < threshold`) bypass the retry and escalate immediately.

## Consequences

- **Positive:** High safety guarantee — two independent mechanisms must both pass.
- **Positive:** Grounding is auditable — the CriticAgent's `<thinking>` block traces claims to specific chunk sources.
- **Negative:** Additional latency per ticket. Mitigated by using Flash-Lite for the CriticAgent.
- **Risk:** The retry loop can triple LLM calls in the worst case. Mitigated by the cap and by aggressive context compression upstream.
