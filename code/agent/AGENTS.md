# code/agent/ — AGENTS.md

The only place that talks to a model. Everything here goes through Claude Code
headless (no API key).

- `client.py` — `run_claude_text` / `run_claude_json`: subprocess `claude -p
  --output-format json --model ... --allowedTools Read --add-dir ...` from a
  neutral cwd (so the nested agent does not load this repo's AGENTS.md), parse the
  JSON envelope's `result`, strip code fences, extract JSON. Exponential-backoff
  retry, `ClaudeError` on repeated failure, content-hash cache.
- `claim_extract.py` — S1: parse the (multilingual) conversation into a claim.
- `perception.py` — S2: one image at a time, "describe before decide", carries the
  untrusted-text guardrail. Returns an `ImageFact`.
- `adjudicate.py` — S3: text-only reasoning over per-image facts + claim + rule +
  history. Drafts the 10 produced columns.
- `critic.py` — S5: grounding/enum/injection-echo validation.

Invariants: every function takes an injectable client (tests pass a fake; no real
`claude` calls in tests). On `ClaudeError`, return a safe conservative default
(undecodable image / NEI draft), never crash the batch. Models are chosen per
stage in `config.py` (Sonnet perception, Opus adjudication, Haiku critic).
