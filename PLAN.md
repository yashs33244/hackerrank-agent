# FINAL PLAN — Orchestrate June 2026: Multi-Modal Evidence Review

> Branch `orchestrate2`. Gates passed: `research/06_self_grill.md` (decisions) + `research/07_eng_review.md` (architecture). Goal: finish **#1**. **No code is written until you say go.**

## 0. Approach in one line
**One Claude-Code-powered agent**, internally **two-stage** (per-image perception → text-only adjudication), wrapped in a **deterministic decision tree + strict CSV formatter**. Images are primary truth; conversation is the question; user-history + authenticity + injection are flags that **never flip `claim_status`**. **Runs entirely through Claude Code (`claude -p --json-schema`), no API key.**

## 1. How we win each rubric dimension (effort follows the weights)

| Dimension | Weight | What we do to max it |
|---|---|---|
| **Output CSV** | **30%** | Deterministic post-processor finalizes every enum (≈0 invalid values); 14-col header copied verbatim; **byte-sniff + normalize the 8 AVIF-as-`.jpg` images** competitors miss; `claim_status`/`risk_flags` calibrated against all 20 labels; **every justification cites specific image IDs** (generic ones cap at ~70%). |
| **Code ZIP** | **30%** (arch 30 · prompt/tool 30 · robustness 25 · rigor 15) | Single-agent + small toolset (the May #1 lever); clean SOLID module tree; **per-folder `AGENTS.md`+`CLAUDE.md`**; Pydantic enum-clamp + retry + safe fallback (robustness); real `evaluation/`, README, deterministic, secrets-free (rigor). |
| **AI Judge Interview** | **30%** (depth 40 · judgment 25 · comm 20 · honesty 15) | Ownership script ("I chose X, I rejected Y, I added the evidence-gate after case_006"); defend the two-axis `valid_image`≠`evidence_standard_met`, "history never overrides pixels", injection-as-architecture; volunteer known failure modes (honesty). Prep doc = blueprint §8 (15 Q&A). |
| **Chat Transcript** | **10%** | `~/hackerrank_orchestrate/log.txt` already shows scoped prompts, a corrected misread, rejected options, verification loops, and you steering provider/architecture decisions. Keep it clean to the end. |

## 2. What we copy from winners / avoid from losers (May post-mortem)
**Copy:** single-agent+tools (beat multi-agent); cheap-model short-circuit for trivial work; deterministic post-processing; "when in doubt, escalate" → here **"when in doubt → `not_enough_information` + `manual_review_required`"**; citation guard (a justification must cite an image we actually inspected); a real eval harness; prompt/context reuse for cost.
**Avoid:** multi-agent zoo; narrating the AI in the interview; thin/absent eval folder; generic justifications; ignoring the image-format trap; over-abstaining (only 2/20 are NEI).

## 3. Target repo layout (branch `orchestrate2`)
Canonical contest layout at root so the zip is submission-ready; old solution preserved.
```
code/                      # NEW solution (every subfolder has AGENTS.md + CLAUDE.md)
  main.py  config.py  pipeline.py  state.py
  domain/  images/  agent/  prompts/  io/  evaluation/
dataset/                   # staged (claims, sample, history, requirements, images)
output.csv                 # 44 predicted rows (generated)
problem_statement.md  AGENTS.md  README.md   # new-contest versions at root
research/                  # all research + gates (00-07) + this PLAN
previous_contest/          # the old support-triage solution, preserved as reference
```
Root `AGENTS.md` keeps the contest's mandatory logging contract; each `code/**/AGENTS.md` states that folder's purpose, I/O, invariants, and rename rules; each `CLAUDE.md` = `@AGENTS.md` + Claude-Code notes. (Pipeline detail: `research/07_eng_review.md §2`.)

## 4. The pipeline (locked) — `research/07_eng_review.md §1`
`S0 normalize/pre-gate (Python)` → `S1 claim extract (Sonnet)` → `S2 per-image perception (Sonnet vision, parallel, cached)` → `S3 adjudication (Opus, text-only)` → `S4 deterministic decision tree (Python)` → `S5 critic/validator` → `S6 strict CSV formatter (Python)`. Decision tree + MRR rule calibrated to all 20 sample labels (incl. the corrected MRR nuance: case_006 NEI gets **no** MRR).

## 5. Execution engine (no API key)
`agent/client.py` subprocesses `claude -p "<prompt>" --output-format json --json-schema <schema> --model <claude-sonnet-4-6|claude-opus-4-8|claude-haiku-4-5> --add-dir <repo> --allowedTools Read`, with backoff retry + content-hash cache. Subscription auth, no per-token cost. Ops report covers call/token estimates, hypothetical API-equivalent (~$0.85), and subscription usage-limit mitigations (cache, cheap-model routing, checkpoint/resume, bounded concurrency).

## 6. Build phases (time-boxed; ~22h to deadline) — submittable artifact by ~hour 6
| Phase | Deliverable | Validates |
|---|---|---|
| **P0 setup** | Restructure branch (old→`previous_contest/`, new root layout); `code/` skeleton + per-folder `AGENTS.md`/`CLAUDE.md`; **smoke-test one `claude -p --json-schema` image call** | engine works, no key |
| **P1 S0 + IO** | image normalize (AVIF/WebP→PNG, **assert 111/111 decode**), history/evidence loaders, claims reader, **S6 formatter writing a header-valid 44-row placeholder `output.csv`** | submittable CSV exists early |
| **P2 S2 perception** | per-image prompt (describe-before-decide, untrusted-text guard), parallel + cache; eyeball sample images | vision facts are sane |
| **P3 S1+S3+S4** | claim extraction, adjudication, deterministic decision tree + risk/MRR union | end-to-end on sample |
| **P4 eval** | `evaluation/`: per-column acc, `claim_status` confusion, `risk_flags` F1, id-set match, per-object; **first full sample score** | accuracy baseline |
| **P5 calibrate (no hardcoding)** | fix systematic biases vs the 20 labels; run **≥2-strategy comparison** (single-pass vs two-stage; ±deterministic post-processor) | pick final config |
| **P6 test run + report** | generate final `output.csv` (44 rows); `evaluation_report.md` (accuracy + comparison + ops) | deliverables done |
| **P7 polish** | `code/` README, transcript hygiene, **rehearse interview Q&A**; commit (author Yash Singh, **no Co-Authored-By**) | submission-ready |

## 7. Definition of done
All four deliverables strong: (1) valid 44-row `output.csv`, 0 enum violations, IDs/format correct; (2) clean `code/` with per-folder docs + README + `evaluation/`, runs via Claude Code with no key; (3) `evaluation_report.md` with metrics, ≥2-strategy comparison, ops analysis; (4) tidy `log.txt`; plus a rehearsed interview.

## 8. Open items (need your OK)
1. **Restructure** the branch (move old solution → `previous_contest/`, adopt new root layout). Non-destructive; `main` untouched. OK?
2. Confirm **commit attribution**: author *Yash Singh*, no `Co-Authored-By` trailer. (Already captured.)
3. On **go**, I start at **P0** and build straight through, checkpointing each phase.
