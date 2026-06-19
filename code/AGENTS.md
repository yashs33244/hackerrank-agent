# code/ — AGENTS.md (solution contract)

The Multi-Modal Evidence Review system. For each row of `dataset/claims.csv` it
produces one row of `output.csv` (14 columns, strict enums) deciding whether the
submitted images `supported` / `contradicted` / `not_enough_information` the
user's damage claim.

## Inference engine: Claude Code, no API key
All model calls go through `agent/client.py`, which subprocesses the local
`claude` CLI in headless mode (`claude -p --output-format json --model ... --allowedTools Read --add-dir ...`)
and authenticates via the user's Claude **subscription**. There is **no API key**
and no `anthropic`/`openai` SDK. Never add one.

## Entry points (do not rename)
- `python code/main.py` — read `dataset/claims.csv`, write `output.csv`.
- `python code/evaluation/main.py` — score against `dataset/sample_claims.csv`.

## Pipeline (one agent identity, internal stages; see research/07_eng_review.md)
Active path: `S0 normalize/pre-gate` → `S1 claim extract` → `S2 per-image
perception` → `S4 deterministic decision tree` → `S6 strict CSV formatter`. LLM
stages propose facts; deterministic Python (`domain/decision_tree.py`,
`dataio/formatter.py`) disposes every scored enum, so invalid values are
impossible by construction.

`agent/adjudicate.py` (S3) and `agent/critic.py` (S5) are implemented but **not
wired** into the active pipeline today: the deterministic tree is the decider.
Wiring S3 in is the documented next step to lift contradicted-recall (see
`evaluation/evaluation_report.md` known limitations).

## Module map
- `config.py` — all env + tunables (models, paths, concurrency, timeouts).
- `domain/` — enums, constants, types, evidence rules, history, decision tree.
- `images/` — byte-sniff + normalize (AVIF/WebP→PNG), authenticity signals, cache.
- `agent/` — Claude Code client + the LLM stages (perception, claim extract, adjudicate, critic).
- `prompts/` — prompt templates (perception carries the untrusted-text guardrail).
- `dataio/` — claims reader, Pydantic output schema + clamp, the single CSV write path.
- `evaluation/` — metrics, scoring harness, strategy comparison.

## Invariants
- Images are primary truth; user history + authenticity + injection are flags
  that **never flip `claim_status`** by themselves.
- Secrets from env only; never hardcode. Reproducibility: a content-hash cache
  pins each per-image perception result, so a given `output.csv` reproduces
  exactly; the deterministic decision tree + single-path formatter make the scored
  columns a pure function of those cached facts. The Claude Code CLI exposes no
  temperature flag, so the cache (not temperature 0) is the reproducibility
  mechanism; fresh, un-cached runs vary by about one row.
- Files ≤400 lines, one responsibility each; enums/constants/types stay separate.
- No em dashes, no emojis in code or comments.
