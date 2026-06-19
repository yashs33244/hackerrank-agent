# Orchestrate June 2026 — Research (branch: `orchestrate2`)

Goal: finish **#1** in HackerRank Orchestrate (June 2026) — **Multi-Modal Evidence Review**.
This folder holds research only. **No solution code is written until explicitly approved**
(and only after the `/grill-me` + `/plan-eng-review` gates).

## The task in one paragraph
For each damage claim (`car | laptop | package`), decide whether the submitted **images**
support / contradict / give `not_enough_information` for the user's claim — using the claim
conversation, user history, and minimum evidence requirements. Output a **14-column** CSV with
strict enums. Images are the primary source of truth. 20 labeled samples, 44 test cases.

## Key clock
- Challenge end: **2026-06-20 11:00 IST**
- Results: **2026-06-29 12:00 IST**

## Deliverables (filled as research completes)
| File | Contents |
|---|---|
| `_spec/` | Raw copies of the new problem statement, AGENTS.md, README |
| `01_prior_contest_intel.md` | How prior Orchestrate finishers approached it + AI-Judge intel (Agent A) |
| `02_technical_landscape.md` | Multimodal SOTA, model choice, cost/latency, authenticity detection (Agent B) |
| `03_dataset_analysis.md` | Empirical label distributions + image→label mapping + edge cases (Agent C) |
| `04_spec_scoring_prior.md` | Exact contract, enum traps, scoring surface, prior-solution reuse (Agent D) |
| `05_winning_blueprint.md` | Synthesized #1 strategy across all 4 rubric dimensions (Agent E) |
| `00_executive_summary.md` | One-page TL;DR with verified facts + the 5 edge moves (start here) |

## Status
- [x] Branch `orchestrate2` created from `main`
- [x] New dataset + spec staged into branch (`dataset/`, `research/_spec/`)
- [x] Research workflow complete (5 agents; run wf_96cbf3d6-185)
- [x] Key empirical claims verified (8 AVIF-as-jpg images, 44-row dist, output.csv stub)
- [ ] Blueprint reviewed with user  ← **you are here**
- [ ] `/grill-me` + `/plan-eng-review` (before any code)
- [ ] Implementation (awaiting explicit go-ahead)

## Verified empirical facts (checked against the real dataset)
- 8 test images are AVIF disguised as `.jpg` (case_001/img_1,img_3; case_005/img_1,img_2; case_018/img_1; case_046/img_2; case_047/img_2; case_051/img_1).
- `claims.csv`: 44 rows; images/row = {1:13, 2:24, 3:7}; objects = {car:18, laptop:13, package:13}.
- `dataset/output.csv` = 239-byte header-only stub (copy header verbatim).
