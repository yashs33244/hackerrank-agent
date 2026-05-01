# Architecture: Multi-Domain Support Triage Agent

## Overview

This system is a multi-agent AI pipeline that resolves support tickets for three companies — **HackerRank**, **Claude**, and **Visa** — using only the provided support corpus. No external knowledge sources are used.

For each incoming ticket the pipeline:
1. Classifies domain, intent, risk, and request type
2. Decides whether to reply or escalate to a human
3. Retrieves the most relevant corpus excerpts
4. Drafts a grounded, user-facing response
5. Quality-checks the draft against the corpus
6. Formats the result into five CSV columns

---

## Agent Architecture

```
Ticket (CSV row)
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│ RouterAgent  [LOW cognitive load — Gemini Flash-Lite]               │
│                                                                     │
│  1. Pattern-match injection attempts (token-free, instant)          │
│  2. LLM call: classify domain / intent / risk_level / request_type  │
│  3. CRITICAL risk → pre-flight escalation (skip downstream)         │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ TicketState
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ TriageAgent  [MEDIUM — Gemini Flash]                                │
│                                                                     │
│  Decide: reply or escalate?                                         │
│  • HIGH / CRITICAL risk → always escalate (safety override)         │
│  • Otherwise: LLM reasons with <thinking> block before output       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               │                         │
               ▼                         ▼
         replied                    escalated
               │                         │
               ▼                         ▼
┌──────────────────────┐     ┌──────────────────────┐
│ ResponderAgent       │     │ Canned escalation    │
│ [MEDIUM/HIGH — Flash │     │ message              │
│ or Pro]              │     └──────────────────────┘
│                      │
│ 1. search_corpus()   │◄── BM25Searcher (hybrid retrieval)
│ 2. compress_context()│◄── LLMContextCompressor
│ 3. Draft response    │
└──────────┬───────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ CriticAgent  [LOW — Gemini Flash-Lite]                              │
│                                                                     │
│  Score: grounding / safety / completeness (0–10 each)              │
│  • All ≥ threshold (7) → pass                                       │
│  • Safety < threshold → force escalation                            │
│  • Any fail → retry ResponderAgent (up to MAX_RESPONDER_CALLS)      │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ TicketState
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ FormatterAgent  [DETERMINISTIC — no LLM]                            │
│                                                                     │
│  Derive 5 CSV columns from TicketState:                             │
│  status | product_area | response | justification | request_type    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Map

```
code/
├── config.py              Centralized typed settings — one import, no scattered os.getenv()
├── domain/
│   ├── enums.py           All constrained value sets (Domain, RiskLevel, TicketStatus…)
│   └── types.py           All dataclasses, TypedDicts, and Protocol interfaces
├── agents/
│   ├── base.py            AbstractAgent ABC with prompt loading, LLM call, JSON parsing
│   ├── gemini_client.py   GeminiClient + GeminiClientFactory (flyweight + retry)
│   ├── router.py          RouterAgent
│   ├── triage.py          TriageAgent
│   ├── responder.py       ResponderAgent
│   ├── critic.py          CriticAgent
│   └── formatter.py       FormatterAgent (pure logic, no LLM)
├── index/
│   ├── build.py           One-time offline index builder
│   ├── search.py          BM25Searcher (implements Searcher Protocol)
│   └── compress.py        LLMContextCompressor (implements ContextCompressor Protocol)
├── pipeline.py            Pipeline orchestrator + PipelineFactory (composition root)
└── main.py                Entry point: CSV → CSV

scripts/           [DEV ONLY — not deliverable]
├── evaluate.py    Scores output.csv vs sample ground truth
└── improve_loop.py Auto-improve prompts via eval → patch → re-run loop

docs/
├── architecture.md  (this file)
└── adr/             Architecture Decision Records
```

---

## Data Flow: TicketState

`TicketState` is the single typed object passed through the entire pipeline. Each agent reads only its relevant fields and writes only its owned fields. This prevents token bloat from passing full reasoning traces between agents.

| Agent | Reads | Writes |
|---|---|---|
| RouterAgent | `ticket, subject, company` | `domain, intent, risk_level, request_type` |
| TriageAgent | `ticket, intent, risk_level, request_type, domain` | `status, triage_reason` |
| ResponderAgent | `ticket, intent, domain, status, risk_level` | `search_result, draft_response` |
| CriticAgent | `ticket, draft_response, retrieved_chunks, status` | `critic_scores` |
| FormatterAgent | all fields | `final_output` |

---

## Retrieval Stack

```
Query
  │
  ▼
BM25 keyword filter  (top 20 candidates, zero LLM cost)
  │
  ▼
Cosine similarity rerank  (when embeddings.npy available)
  │
  ▼
Top-3 chunks → LLMContextCompressor (Flash-Lite)
  │
  ▼
Compressed context → ResponderAgent
```

The index is **pre-built and committed** (`code/index/data/`) for deterministic, fast startup. Embeddings use `models/gemini-embedding-001`.

---

## Model Routing

| Agent | Cognitive Load | Model |
|---|---|---|
| RouterAgent | LOW | `gemini-3.1-flash-lite-preview` |
| ContextCompressor | LOW | `gemini-3.1-flash-lite-preview` |
| CriticAgent | LOW | `gemini-3.1-flash-lite-preview` |
| TriageAgent | MEDIUM | `gemini-3-flash-preview` |
| ResponderAgent (standard) | MEDIUM | `gemini-3-flash-preview` |
| ResponderAgent (high risk) | HIGH | `gemini-3.1-pro-preview` |

All model names are configured in `.env` and loaded via `config.py`. No hardcoded model strings exist in agent code.

---

## Safety Design

Two independent safety gates prevent unsafe or injected content from reaching users:

**Gate 1 — RouterAgent (pre-flight)**
- Regex scan for injection patterns (`ignore previous`, `reveal system prompt`, `rm -rf`, etc.)
- Happens before any LLM call — zero token cost
- CRITICAL risk → immediate escalation, no downstream agents run

**Gate 2 — CriticAgent (post-draft)**
- LLM evaluates the draft on `safety` (0–10)
- `safety < 7` → forced escalation regardless of other scores
- Also catches factual hallucination (`grounding < 7` → retry)

---

## SOLID Principle Mapping

| Principle | Implementation |
|---|---|
| Single Responsibility | Each agent class has exactly one pipeline stage responsibility |
| Open / Closed | New agent = new subclass of AbstractAgent; no existing code changes |
| Liskov Substitution | Any agent can be replaced by a compatible subclass |
| Interface Segregation | `Searcher`, `ContextCompressor`, `LLMClient` protocols are narrowly scoped |
| Dependency Inversion | Agents depend on Protocols; concrete implementations injected by `PipelineFactory` |

---

## Design Patterns

| Pattern | Where Used |
|---|---|
| Template Method | `AbstractAgent.run()` defines skeleton; subclasses implement `run()` |
| Factory | `GeminiClientFactory` and `PipelineFactory` |
| Flyweight | `GeminiClientFactory` caches one client per cognitive-load tier |
| Strategy | `Searcher` and `ContextCompressor` injected into `ResponderAgent` |
| Chain of Responsibility | Five agents in sequence, each processing and passing `TicketState` |

---

## Configuration Reference

All settings live in `.env` and are typed in `config.py`:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | (required) | Gemini API authentication |
| `MODEL_LOW` | `models/gemini-3.1-flash-lite-preview` | Low-load agents |
| `MODEL_MEDIUM` | `models/gemini-3-flash-preview` | Medium-load agents |
| `MODEL_HIGH` | `models/gemini-3.1-pro-preview` | High-risk responder |
| `EMBEDDING_MODEL` | `models/gemini-embedding-001` | Index embeddings |
| `BM25_TOP_K` | `20` | BM25 candidate pool size |
| `SEMANTIC_TOP_K` | `5` | Post-rerank pool |
| `FINAL_TOP_K` | `3` | Chunks passed to Responder |
| `MAX_RESPONDER_CALLS` | `3` | Responder/Critic loop cap |
| `CRITIC_PASS_THRESHOLD` | `7` | Min score for each dimension |
