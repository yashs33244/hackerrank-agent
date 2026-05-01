# HackerRank Orchestrate — Multi-Domain Support Triage Agent

> Built for the **HackerRank Orchestrate** 24-hour hackathon (May 1–2, 2026).

A production-grade, multi-agent AI pipeline that triages real support tickets across three product ecosystems — **HackerRank**, **Claude (Anthropic)**, and **Visa** — using only the provided support corpus. No hallucinated knowledge, no live web calls.

---

## What Was Built

A five-stage agentic pipeline where each stage is a single-responsibility agent, communicating through a shared typed state object (`TicketState`). For every incoming support ticket, the pipeline:

1. **Routes** — classifies domain, intent, risk level, request type, and product area
2. **Triages** — decides reply vs. escalate with explicit reasoning
3. **Retrieves** — hybrid BM25 + semantic search over the corpus, then LLM-compresses context
4. **Responds** — drafts a grounded, user-facing response (Agentic RAG)
5. **Critiques** — scores the draft on grounding, safety, and completeness; retries if below threshold
6. **Formats** — maps final state to the 5 required CSV output columns

**Output per ticket:**


| Column          | Values                                                                |
| --------------- | --------------------------------------------------------------------- |
| `status`        | `replied` / `escalated`                                               |
| `product_area`  | specific corpus category (e.g. `screen`, `privacy`, `travel_support`) |
| `response`      | user-facing answer grounded in the corpus                             |
| `justification` | concise routing/answering decision explanation                        |
| `request_type`  | `product_issue` / `feature_request` / `bug` / `invalid`               |


---

## Architecture

```
Ticket (CSV row)
     │
     ▼
┌──────────────────────────────────────────────────────────────────┐
│ RouterAgent  [LOW — Gemini Flash-Lite]                           │
│  • Regex injection scan (zero LLM cost)                          │
│  • Classify: domain / intent / risk_level / request_type /       │
│    product_area                                                   │
│  • CRITICAL risk → immediate pre-flight escalation               │
└──────────────────────────┬───────────────────────────────────────┘
                           │ TicketState
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ TriageAgent  [MEDIUM — Gemini Flash]                             │
│  • <thinking> block before output                                │
│  • Service outages / active fraud → ESCALATE                     │
│  • Everything answerable from corpus → REPLY                     │
└──────────────────────────┬───────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
        replied                   escalated
              │                         │
              ▼                         ▼
┌─────────────────────────┐   ┌────────────────────┐
│ ResponderAgent           │   │ Canned escalation  │
│ [MEDIUM/HIGH — Flash/Pro]│   │ message            │
│  1. search_corpus()      │   └────────────────────┘
│  2. compress_context()   │
│  3. Draft response       │
└────────────┬────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ CriticAgent  [LOW — Gemini Flash-Lite]                           │
│  Score: grounding / safety / completeness (0–10 each)           │
│  • safety < 7 → force escalation                                 │
│  • any < threshold → retry Responder (up to 3 times)             │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ FormatterAgent  [DETERMINISTIC — no LLM]                         │
│  Derive 5 CSV columns from TicketState                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
.
├── code/
│   ├── main.py                  Entry point: reads CSV → runs pipeline → writes output.csv
│   ├── cli.py                   CLI: single-ticket, batch, and interactive REPL modes
│   ├── mcp_server.py            MCP server (JSON-RPC 2.0) for Claude Code / Cursor integration
│   ├── discover_models.py       Queries live Gemini/Anthropic/OpenAI APIs for current models
│   ├── config.py                Centralized typed settings — single import, no scattered os.getenv()
│   ├── pipeline.py              Pipeline orchestrator + PipelineFactory (composition root)
│   ├── domain/
│   │   ├── enums.py             All constrained value sets (Domain, RiskLevel, TicketStatus…)
│   │   └── types.py             All dataclasses, TypedDicts, and Protocol interfaces
│   ├── agents/
│   │   ├── base.py              AbstractAgent ABC — prompt loading, LLM call, JSON parsing
│   │   ├── gemini_client.py     GeminiClient + GeminiClientFactory (flyweight + backoff retry)
│   │   ├── router.py            RouterAgent
│   │   ├── triage.py            TriageAgent
│   │   ├── responder.py         ResponderAgent (Agentic RAG)
│   │   ├── critic.py            CriticAgent
│   │   └── formatter.py         FormatterAgent (pure logic, no LLM)
│   ├── index/
│   │   ├── build.py             One-time offline index builder
│   │   ├── search.py            BM25Searcher with cosine-similarity reranking
│   │   ├── compress.py          LLMContextCompressor
│   │   └── data/                Pre-built index: chunks.jsonl, embeddings.npy, bm25_corpus.txt
│   ├── prompts/
│   │   ├── router.md            Router system prompt (full taxonomy + calibration examples)
│   │   ├── triage.md            Triage system prompt (reply-first, explicit escalation criteria)
│   │   ├── responder.md         Responder system prompt (Agentic RAG + safety guardrails)
│   │   └── critic.md            Critic system prompt (grounding / safety / completeness rubric)
│   ├── tests/
│   │   ├── test_state.py        Unit tests for TicketState dataclass
│   │   └── test_search.py       Unit tests for BM25Searcher
│   └── requirements.txt
├── scripts/                     [DEV ONLY — not part of submission]
│   ├── evaluate.py              Scores output against 10-ticket sample ground truth
│   └── improve_loop.py          Auto-improving loop: eval → LLM patch prompts → re-run
├── docs/
│   ├── architecture.md          Full architecture: module map, data flow, retrieval stack
│   ├── optimization-log.md      All changes made, honest accuracy analysis
│   └── adr/                     8 Architecture Decision Records
│       ├── 0001-agentic-rag.md
│       ├── 0002-model-routing.md
│       ├── 0003-hybrid-retrieval.md
│       ├── 0004-two-gate-feedback-loop.md
│       ├── 0005-offline-index.md
│       ├── 0006-typed-shared-state.md
│       ├── 0007-structured-prompts.md
│       └── 0008-solid-oop-design.md
├── .gemini/skills/support-triage/SKILL.md   Gemini CLI skill
├── .mcp.json                    MCP auto-discovery for Claude Code / Cursor
├── .env.example                 Copy to .env and add your API key
└── support_tickets/
    ├── support_issues.csv       Full ticket set (29 tickets)
    └── output.csv               Agent predictions (submitted file)
```

---

## Setup & Usage

### 1. Install dependencies

```bash
cd code
python3 -m pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key_here
```

### 3. Run on all tickets

```bash
python3 code/main.py
# Writes results to support_tickets/output.csv
```

### 4. Single ticket (CLI)

```bash
python3 code/cli.py --ticket "I can't log in to my HackerRank account" --company HackerRank
```

### 5. Interactive REPL

```bash
python3 code/cli.py --interactive
```

### 6. Discover latest available models (live API query)

```bash
python3 code/discover_models.py
# Add --write-env to auto-update .env with recommended models
python3 code/discover_models.py --write-env
```

---

## Model Routing

Models are assigned by cognitive load — not hardcoded in agent code, loaded from `.env` via `config.py`:


| Tier   | Model                           | Agents                                         |
| ------ | ------------------------------- | ---------------------------------------------- |
| LOW    | `gemini-3.1-flash-lite-preview` | RouterAgent, CriticAgent, ContextCompressor    |
| MEDIUM | `gemini-3-flash-preview`        | TriageAgent, ResponderAgent (standard tickets) |
| HIGH   | `gemini-3.1-pro-preview`        | ResponderAgent (high-risk tickets only)        |
| EMBED  | `gemini-embedding-2`            | Corpus index embeddings (April 2026 GA)        |


All model names are verified by querying the Gemini API live — not hardcoded guesses. Run `python3 code/discover_models.py` to check current availability.

---

## Retrieval Stack

```
Query (reformulated by LLM from intent + domain)
  │
  ▼
BM25 keyword filter        top-20 candidates, zero LLM cost
  │
  ▼
Cosine similarity rerank   using pre-built embeddings.npy
  │
  ▼
Top-3 chunks → LLMContextCompressor (Flash-Lite)
  │
  ▼
Compressed context → ResponderAgent
```

The index is pre-built and committed (`code/index/data/`) for deterministic, fast startup. No corpus processing at runtime.

---

## Safety Design

Two independent safety gates:

**Gate 1 — RouterAgent (pre-flight, zero token cost)**

- Regex scan for injection patterns before any LLM call
- CRITICAL risk → immediate escalation, all downstream agents skipped

**Gate 2 — CriticAgent (post-draft)**

- LLM scores draft on `safety` (0–10)
- `safety < 7` → forced escalation, response discarded
- `grounding < 7` → retry Responder (up to 3 attempts)

---

## Integration as a CLI Plugin / Skill

The agent is designed to work as a skill/plugin for any AI CLI tool:

### Gemini CLI

The `.gemini/skills/support-triage/SKILL.md` skill is auto-loaded when you open Gemini CLI in this directory:

```
/support-triage triage this ticket: "I can't log into my account"
```

### Claude Code / Cursor

The `.mcp.json` file auto-registers the `triage_ticket` MCP tool. Start the server with:

```bash
python3 code/mcp_server.py
```

Then call it from Claude Code or Cursor as a tool: `triage_ticket(ticket="...", company="...")`.

### OpenAI Codex CLI

Run as a subprocess tool:

```bash
codex exec -- python3 code/cli.py --ticket "$TICKET" --company "$COMPANY"
```

---

## Accuracy & Results

### Labelled evaluation (10 sample tickets with ground truth)


| Dimension        | Score            |
| ---------------- | ---------------- |
| Status match     | 10/10            |
| Product area     | 10/10            |
| Request type     | 10/10            |
| Response quality | 10/10            |
| **Overall**      | **40/40 = 100%** |


### Proxy metrics — all 29 tickets


| Metric                           | Result       |
| -------------------------------- | ------------ |
| Zero crashes / errors            | 29/29 (100%) |
| Substantive response (>50 chars) | 29/29 (100%) |
| Avg critic grounding score       | 9.6 / 10     |
| Avg critic safety score          | 10.0 / 10    |
| Avg critic completeness score    | 9.9 / 10     |
| Critic pass rate (all dims ≥ 7)  | 21/21 (100%) |


> **Honest note:** The 100% on 10 samples reflects iterative tuning against that specific sample set — effective overfitting. Real-world accuracy for this class of system is ~72–85% depending on the dimension. See `[docs/optimization-log.md](./docs/optimization-log.md)` for the full honest breakdown.

---

## Documentation Summary

### `[docs/architecture.md](./docs/architecture.md)`

Full technical architecture: agent pipeline diagram, module map, TicketState data flow table, retrieval stack, model routing table, two-gate safety design, SOLID principle mapping, and design pattern inventory. Start here to understand how the system works end-to-end.

### `[docs/optimization-log.md](./docs/optimization-log.md)`

Complete optimization history across 4 iterations (baseline ~40% → 65% → 80% → 95% → 100% on sample). Documents every prompt change, code fix, and the reasoning behind each decision. Includes an honest accuracy disclaimer, real-world accuracy estimates, and the full proxy metrics report for all 29 tickets.

### `[docs/adr/0001-agentic-rag.md](./docs/adr/0001-agentic-rag.md)`

Why Agentic RAG was chosen over standard RAG. The ResponderAgent reformulates queries based on classified intent/domain rather than using raw ticket text — producing more targeted retrieval and auditable source attribution.

### `[docs/adr/0002-model-routing.md](./docs/adr/0002-model-routing.md)`

Why each agent is assigned a specific Gemini model tier. Balances cost, speed, and capability — Flash-Lite for structured extraction, Flash for reasoning, Pro only for high-risk responses.

### `[docs/adr/0003-hybrid-retrieval.md](./docs/adr/0003-hybrid-retrieval.md)`

Why hybrid BM25 + cosine similarity reranking was chosen over pure vector search. BM25 handles exact term matching (product names, error codes) while semantic reranking handles paraphrase and intent-matching.

### `[docs/adr/0004-two-gate-feedback-loop.md](./docs/adr/0004-two-gate-feedback-loop.md)`

Why there are two independent safety gates (pre-flight regex + post-draft Critic). Defense in depth: the pre-flight gate catches injections at zero cost; the Critic gate catches hallucinations and unsafe content after drafting.

### `[docs/adr/0005-offline-index.md](./docs/adr/0005-offline-index.md)`

Why the corpus index is pre-built and committed rather than built at runtime. Ensures deterministic startup, eliminates per-run embedding cost, and makes the submission reproducible without re-indexing.

### `[docs/adr/0006-typed-shared-state.md](./docs/adr/0006-typed-shared-state.md)`

Why `TicketState` is a single typed dataclass passed through the pipeline rather than each agent returning its own dict. Prevents field name collisions, enables IDE type checking, and makes the data flow inspectable at any stage.

### `[docs/adr/0007-structured-prompts.md](./docs/adr/0007-structured-prompts.md)`

Why prompts use a layered XML tag structure (`<identity>`, `<security_protocol>`, `<mission>`, `<output_format>`). Inspired by leaked Anthropic/Claude system prompt patterns — structured tags reduce instruction-following failures and make prompt sections independently editable.

### `[docs/adr/0008-solid-oop-design.md](./docs/adr/0008-solid-oop-design.md)`

How SOLID principles are applied: `AbstractAgent` ABC (SRP + OCP), narrowly scoped `LLMClient`/`Searcher`/`ContextCompressor` Protocols (ISP), `PipelineFactory` for dependency injection (DIP), and the Flyweight pattern in `GeminiClientFactory`.

---

## Engineering Standards

- **Zero scattered `os.getenv()`** — all config in `config.py` as a frozen `Settings` dataclass
- **All constrained values as enums** — `Domain`, `RiskLevel`, `TicketStatus`, `RequestType`, `CognitiveLoad` in `domain/enums.py`
- **All interfaces as Protocols** — `LLMClient`, `Searcher`, `ContextCompressor` in `domain/types.py`
- **SOLID principles** enforced: AbstractAgent ABC, PipelineFactory DI, narrowly-scoped Protocols
- **Exponential backoff** in `GeminiClient` for 429 rate limit errors
- **Tests** in `code/tests/` for core data structures and retrieval
- **No hardcoded model names** in agent code — all loaded from `.env` via `config.py`

---

## Environment Variables


| Variable                | Default                                | Purpose                             |
| ----------------------- | -------------------------------------- | ----------------------------------- |
| `GEMINI_API_KEY`        | *(required)*                           | Gemini API authentication           |
| `MODEL_LOW`             | `models/gemini-3.1-flash-lite-preview` | Low cognitive load agents           |
| `MODEL_MEDIUM`          | `models/gemini-3-flash-preview`        | Medium cognitive load agents        |
| `MODEL_HIGH`            | `models/gemini-3.1-pro-preview`        | High-risk responder                 |
| `EMBEDDING_MODEL`       | `models/gemini-embedding-2`            | Corpus index embeddings             |
| `BM25_TOP_K`            | `20`                                   | BM25 candidate pool size            |
| `SEMANTIC_TOP_K`        | `5`                                    | Post-rerank pool size               |
| `FINAL_TOP_K`           | `3`                                    | Chunks passed to Responder          |
| `MAX_RESPONDER_CALLS`   | `3`                                    | Responder/Critic retry cap          |
| `CRITIC_PASS_THRESHOLD` | `7`                                    | Minimum passing score per dimension |


---

## Dev Scripts (not part of deliverable)

```bash
# Score against 10-ticket sample ground truth
python3 scripts/evaluate.py

# Run the auto-improvement loop (eval → LLM patches prompts → re-run)
python3 scripts/improve_loop.py --iterations 3
```

See `[scripts/README.md](./scripts/README.md)` for full usage.