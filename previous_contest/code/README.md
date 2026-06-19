# HackerRank Orchestrate — Support Triage Agent

A multi-agent, context-engineered support triage system for HackerRank, Claude, and Visa support tickets.

## Architecture

```
Ticket Input
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  RouterAgent (gemini-2.0-flash)                     │
│  • Domain classification (hackerrank/claude/visa)   │
│  • Pre-flight safety screen (injection detection)   │
│  • risk_level: LOW / MEDIUM / HIGH / CRITICAL       │
└────────────────────┬────────────────────────────────┘
                     │ CRITICAL → escalate immediately
                     ▼
┌─────────────────────────────────────────────────────┐
│  TriageAgent (gemini-2.5-pro)                       │
│  • replied vs escalated decision                    │
│  • Forced <thinking> reasoning before output        │
└────────────────────┬────────────────────────────────┘
                     │ replied only
                     ▼
┌─────────────────────────────────────────────────────┐
│  ResponderAgent (gemini-2.5-pro / 2.0-flash-high)  │
│  • Calls search_corpus() as a tool (Agentic RAG)   │
│  • BM25 → semantic rerank → LLM compression        │
│  • Hard cap: 3 retrieval+generation calls           │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  CriticAgent (gemini-2.0-flash)                     │
│  • Scores: grounding / safety / completeness (0-10) │
│  • Pass threshold: all ≥ 7                          │
│  • Safety < 7 → force escalate                      │
│  • Grounding/completeness < 7 → retry Responder     │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  FormatterAgent (pure logic, no LLM)                │
│  • Produces exactly 5 CSV output columns            │
│  • Derives product_area from corpus source path     │
│  • Builds justification from critic scores          │
└─────────────────────────────────────────────────────┘
                     │
                     ▼
              output.csv
```

## Key Design Decisions


| Decision       | Choice                                   | Rationale                                            |
| -------------- | ---------------------------------------- | ---------------------------------------------------- |
| RAG type       | Agentic (tool-based)                     | Agent decides what to retrieve, not static pre-fetch |
| Retrieval      | BM25 → semantic rerank → LLM compression | Token-efficient: only inject relevant sentences      |
| Orchestration  | Typed `TicketState`                      | Each agent sees only its slice — no token bloat      |
| Feedback       | 2-gate (Router + Critic)                 | Cheap pre-flight + quality-gated post-draft          |
| Model routing  | Flash (low) → Pro (medium/high)          | Cost-efficient; Opus only for HIGH risk              |
| System prompts | Layered B/C pattern + security guardrail | Injection-resistant, reasoning-transparent           |


## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API key
cp ../.env.example ../.env
# Edit .env: set GEMINI_API_KEY=your_key

# 3. Build the corpus index (one-time, ~4 minutes)
python -m index.build
```

## Usage Modes

All commands are run from the **repo root**.

### 1. Batch CSV (original entry point)

```bash
python code/main.py
```

Reads `support_tickets/support_tickets.csv`, writes `support_tickets/output.csv`.

### 2. Single ticket — CLI

```bash
python code/cli.py --ticket "I can't log in to my account" --company HackerRank
python code/cli.py --ticket "Billing charge dispute" --company Visa --subject "Charge query"
```

Prints a JSON object to stdout:

```json
{
  "status": "replied",
  "product_area": "hackerrank/account",
  "response": "...",
  "justification": "...",
  "request_type": "account_access"
}
```

### 3. Batch CSV via CLI (custom paths)

```bash
python code/cli.py --csv support_tickets/support_tickets.csv
python code/cli.py --csv /path/to/tickets.csv --output /tmp/results.csv
```

Same pipeline as `main.py`, with configurable input/output paths.

### 4. Interactive REPL

```bash
python code/cli.py --interactive
```

Prompts for ticket text, company, and subject; prints JSON after each ticket. Type `exit` to quit.

### 5. MCP Server (Claude Code / Cursor / Gemini CLI)

```bash
python code/mcp_server.py
```

Starts an MCP stdio server exposing the `triage_ticket` tool. Claude Code and Cursor
auto-discover it via `.mcp.json` at the repo root — no manual configuration needed.

**Manual registration** (if auto-discovery is not available):

```json
// .mcp.json  (already present at repo root)
{
  "mcpServers": {
    "hackerrank-triage-agent": {
      "command": "python",
      "args": ["code/mcp_server.py"]
    }
  }
}
```

**Tool signature:**

```
triage_ticket(ticket: str, company?: str, subject?: str) -> TicketOutput
```

**Example MCP call** (raw JSON-RPC for testing):

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"triage_ticket","arguments":{"ticket":"I cannot submit my solution","company":"HackerRank"}}}' \
  | python code/mcp_server.py
```

### CLI quick reference

| Flag | Short | Description |
|---|---|---|
| `--ticket TEXT` | `-t` | Single ticket text |
| `--company NAME` | `-c` | Company (HackerRank \| Claude \| Visa) |
| `--subject TEXT` | `-s` | Subject line |
| `--csv FILE` | `-f` | Batch CSV input |
| `--output FILE` | `-o` | Batch CSV output path |
| `--interactive` | `-i` | Interactive REPL |

## Project Structure

```
code/
├── main.py              # Batch CSV entry point (original)
├── cli.py               # CLI entry point (--ticket / --csv / --interactive)
├── mcp_server.py        # MCP stdio server (Claude Code / Cursor / Gemini CLI)
├── pipeline.py          # Orchestrator: wires agents + retry loop
├── config.py            # Centralized settings (env vars, paths, model names)
├── state.py             # TicketState dataclass
├── agents/
│   ├── _base.py         # Gemini client factory + prompt loader
│   ├── router.py        # RouterAgent — domain + pre-flight screen
│   ├── triage.py        # TriageAgent — escalate vs reply
│   ├── responder.py     # ResponderAgent — corpus-grounded answer
│   ├── critic.py        # CriticAgent — 3-axis quality gate
│   └── formatter.py     # FormatterAgent — 5-column CSV output
├── index/
│   ├── build.py         # Offline index builder (run once)
│   ├── search.py        # BM25Searcher — hybrid retrieval
│   └── compress.py      # LLM-based context compression
├── prompts/
│   ├── router.md        # RouterAgent system prompt
│   ├── triage.md        # TriageAgent system prompt
│   ├── responder.md     # ResponderAgent system prompt
│   └── critic.md        # CriticAgent system prompt
├── tests/
│   ├── test_state.py    # TicketState behavior tests
│   └── test_search.py   # BM25Searcher behavior tests
└── requirements.txt

.mcp.json                # MCP auto-discovery (Claude Code / Cursor)
```

## Running Tests

```bash
python -m pytest tests/ -v
```

All tests are pure unit tests — no API calls, no index required.

## Token Optimization Strategy

1. **BM25 pre-filter** eliminates ~95% of irrelevant chunks before any LLM call
2. **Semantic rerank** selects top-3 from BM25 survivors (no embedding at inference — index pre-built)
3. **LLM compression** extracts only relevant sentences from chunks (~70% reduction)
4. **Scoped TicketState** — each agent receives only its relevant fields, not the full conversation history
5. **Model routing** — Flash for low-load tasks, Pro only where reasoning depth matters
6. **Pre-flight escalation** — CRITICAL tickets never reach the Responder (zero Sonnet tokens spent)

