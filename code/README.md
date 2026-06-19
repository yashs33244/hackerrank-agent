# Multi-Modal Evidence Review

A system that verifies damage claims (`car` | `laptop` | `package`) by inspecting
the submitted images, the claim conversation, the user's history, and the minimum
evidence requirements, then writes a 14-column `output.csv`. The **images are the
primary source of truth**; user history and image authenticity are risk signals
that never flip the verdict by themselves.

## No API key: runs on Claude Code

All model calls go through the local `claude` CLI in headless mode under your
Claude **subscription** (`agent/client.py`). There is no API key and no
`anthropic`/`openai` SDK. You only need the `claude` CLI installed and signed in.

## Quickstart

```bash
# Predictions for the 44 test rows -> output.csv
python code/main.py

# Predictions for the 20 labeled rows -> sample_output.csv
python code/main.py --sample

# Score a prediction file against the gold labels
python code/evaluation/main.py sample_output.csv dataset/sample_claims.csv

# Quick smoke run (first N rows)
python code/main.py --limit 3
```

Requirements: Python 3.12, Pillow, Pydantic v2, ImageMagick (`magick`/`convert`,
for AVIF -> PNG), and the `claude` CLI. Tests: `python -m pytest -q tests/`.

## Architecture (one agent, internal stages)

```
claims.csv row + user_history + evidence_requirements + images
  -> S0 normalize/pre-gate   (byte-sniff, AVIF/WebP->PNG, resize 1024, EXIF/pHash)
  -> S1 claim extract        (Sonnet: multilingual conversation -> structured claim)
  -> S2 per-image perception (Sonnet: claim-aware-but-skeptical objective facts)
  -> S4 deterministic tree   (supported/contradicted/NEI + flags + severity)
  -> S6 strict CSV formatter (14 cols, enum-clamped, the single write path)
```

LLM stages propose facts; the deterministic decision tree and formatter dispose
the final scored enums, so invalid output values are impossible by construction.
Each subfolder has its own `AGENTS.md` describing its job and invariants.

## Key design decisions

- **Byte-level image normalization.** Extensions lie: 8 test `.jpg` files are
  really AVIF that break naive loaders. Every image is sniffed and normalized to
  PNG before any vision call.
- **`valid_image` and `evidence_standard_met` are independent axes** (trust vs
  coverage); a clear image can still be non-original.
- **`manual_review_required`** fires only on history-risk, mismatch, wrong-object,
  authenticity, injection, or unusable images, not on a benign coverage gap.
- **In-image prompt-injection defense:** image text is transcribed as untrusted
  data and flagged (`text_instruction_present`); the verdict is judged on pixels.
- **Claim-aware-but-skeptical perception:** the claim points the model at the part
  to inspect, but the model is instructed to verify damage independently (best of
  the three measured strategies; see `evaluation/evaluation_report.md`).

## Results (sample, n=20)

`claim_status` 0.85 (Wilson 95% CI [0.64, 0.95], stratified 5-fold 0.833 +/- 0.139),
`object_part` 0.80, `issue_type` 0.75, `evidence_standard_met` 0.95. Full metrics,
the >=2-strategy comparison, the operational/cost analysis, and the n=20
methodology are in [`evaluation/evaluation_report.md`](evaluation/evaluation_report.md).

## Layout

```
code/
  main.py  pipeline.py  config.py  cache.py
  domain/   enums, constants, types, evidence_rules, history, decision_tree
  images/   normalize, authenticity
  agent/    client (claude CLI), claim_extract, perception, adjudicate, critic
  prompts/  perception, claim_extract, adjudicate, critic
  dataio/   reader, schema (Pydantic + clamp), formatter
  evaluation/ metrics, cross_validation, main, compare, evaluation_report.md
```
