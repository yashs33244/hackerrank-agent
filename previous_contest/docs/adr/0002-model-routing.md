# ADR-0002: Cognitive-Load-Based Model Routing

**Status:** Accepted  
**Date:** 2026-05-01

## Context

Multiple Gemini model tiers are available with different cost, speed, and capability profiles:

- `gemini-3.1-flash-lite-preview` — fastest, cheapest, limited reasoning
- `gemini-3-flash-preview` — balanced, frontier-class at medium speed
- `gemini-3.1-pro-preview` — most capable, supports extended thinking traces

The pipeline has five agents with different reasoning demands.

## Decision

Assign models to agents based on the minimum cognitive load required for correctness:

| Cognitive Load | Model | Assigned Agents |
|---|---|---|
| LOW | Flash-Lite | RouterAgent, CriticAgent, ContextCompressor |
| MEDIUM | Flash | TriageAgent, ResponderAgent (standard) |
| HIGH | Pro | ResponderAgent (when `risk_level == HIGH`) |

## Rationale

- **RouterAgent** runs a JSON extraction task over a short ticket. Flash-Lite is sufficient.
- **CriticAgent** scores three dimensions; Flash-Lite handles structured scoring well.
- **ContextCompressor** performs extractive summarization — a low-complexity task.
- **TriageAgent** makes a binary decision with multi-factor reasoning — Flash is appropriate.
- **ResponderAgent** drafts a multi-paragraph user-facing reply from compressed context. Flash handles standard tickets; Pro is reserved for HIGH risk tickets that carry elevated legal or safety stakes.

## Consequences

- **Positive:** Significant token cost reduction. Flash-Lite calls cost ~10x less than Pro. High-volume deployments remain viable.
- **Positive:** Faster turnaround for the majority of tickets.
- **Negative:** Pro model has stricter rate limits. Mitigated by exponential backoff in `GeminiClient`.
- **Risk:** Flash-Lite may miss subtle nuances in critic scoring. Mitigated by the Responder/Critic retry loop.
