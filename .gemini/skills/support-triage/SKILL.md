---

## name: support-triage

description: >
  Multi-domain AI support ticket triage agent for HackerRank, Claude (Anthropic), and Visa.
  Classifies tickets, retrieves corpus evidence, decides reply vs escalate, and generates
  grounded responses. Use when you need to triage support tickets, run the pipeline, evaluate
  output quality, or improve the agent's prompts. Triggers on: "triage this ticket",
  "run the pipeline", "evaluate output", "improve the agent", "support ticket".

# Support Triage Agent Skill

This skill helps you work with the multi-domain support triage pipeline in this repository.

## What this agent does

Given a support ticket (text + company), the pipeline:

1. **RouterAgent** — classifies domain, intent, risk, product_area, request_type
2. **TriageAgent** — decides replied vs escalated
3. **ResponderAgent** — retrieves corpus evidence and drafts a grounded response
4. **CriticAgent** — scores grounding / safety / completeness (0–10 each)
5. **FormatterAgent** — produces the 5 CSV output columns

## Quick commands

### Triage a single ticket

```bash
cd code
python cli.py --ticket "I can't log in to my HackerRank account" --company HackerRank
```

### Run on full CSV batch

```bash
python code/main.py
# Output: support_tickets/output.csv
```

### Interactive REPL

```bash
python code/cli.py --interactive
```

### MCP server (for other AI tools)

```bash
python code/mcp_server.py
# Exposes: triage_ticket(ticket, company, subject) via stdio JSON-RPC 2.0
```

### Evaluate against ground truth

```bash
python scripts/evaluate.py
# Scores output against support_tickets/sample_support_tickets.csv
```

### Auto-improve prompts (iterative)

```bash
python scripts/improve_loop.py --agent triage --iterations 3
```

### Discover real available models

```bash
python code/discover_models.py --provider gemini
python code/discover_models.py --provider all      # needs all API keys in .env
python code/discover_models.py --write-env         # auto-updates .env with best models
```

### Rebuild the corpus index (if data changes)

```bash
python code/index/build.py
```

## Architecture overview

```
Router (Flash-Lite) → Triage (Flash) → Responder (Flash/Pro) ↔ Critic (Flash-Lite) → Formatter
                                                    ↑
                                            BM25Searcher + LLMContextCompressor
```

All models are configured in `.env`. Run `python code/discover_models.py` to get real
model names from the Gemini API rather than guessing.

## Key files


| File                       | Purpose                                      |
| -------------------------- | -------------------------------------------- |
| `code/config.py`           | Centralized typed settings                   |
| `code/domain/enums.py`     | All domain enums                             |
| `code/domain/types.py`     | All dataclasses + Protocols                  |
| `code/agents/router.py`    | Domain + product_area classification         |
| `code/agents/triage.py`    | Escalate vs reply decision                   |
| `code/agents/responder.py` | Corpus-grounded response generation          |
| `code/agents/critic.py`    | Grounding/safety/completeness scoring        |
| `code/prompts/*.md`        | Editable system prompts for each agent       |
| `code/index/data/`         | Pre-built search index (chunks + embeddings) |
| `docs/architecture.md`     | Full architecture documentation              |
| `docs/adr/`                | Architecture Decision Records                |


## When Gemini CLI calls this skill

You can ask me to:

- "Triage this ticket: [ticket text]" → runs cli.py and returns JSON
- "Run the full pipeline" → runs main.py on support_tickets.csv
- "What is the current eval score?" → runs evaluate.py and reports
- "Improve the triage prompt" → runs improve_loop.py --agent triage
- "What models are available?" → runs discover_models.py
- "Show the architecture" → reads docs/architecture.md

