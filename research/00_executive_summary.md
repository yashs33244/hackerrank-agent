# Executive Summary — How to finish #1 (Orchestrate June 2026)

> One-page TL;DR over the 5 detailed research files. Research only; no code until approved + gates.

## Verified facts (checked against the real dataset, not just inferred)
- **Scoring is 4 signals, ~30/30/30/10** (Output CSV / Code ZIP / AI Judge Interview / Chat Transcript). Source: HackerRank's own May post-mortem blog + reused June deliverable list. *Weights for June are [THIN] — verify in `/grill-me`.*
- **No single May metric correlated >0.45; every Top-10 was top-quartile on all four.** You cannot win on CSV alone — balance wins.
- **The actual May #1 winner** (Saai Syvendra) published repo + writeup. His recipe: **single agent + small toolset** (he *rejected* multi-agent), cheap-model short-circuit, hybrid retrieval, deterministic post-processing, "when in doubt, escalate." HackerRank confirmed single-agent+tools beat multi-agent pipelines.
- **8 test images are AVIF disguised as `.jpg`** (verified): silently break naive loaders → ~18% of the test set mislabeled. The `.jpg` files are really JPEG/PNG/WEBP/AVIF mixed. **Byte-sniff + normalize all images** = quiet edge most teams miss.
- **44 test rows**, 82 images (13 single / 24 two / 7 three-image); objects car 18 / laptop 13 / package 13. `output.csv` is a header-only stub — copy the 14-col header verbatim.
- **Adversarial content is present:** in-image prompt injection ("approve this claim"), watermarked/non-original (Vecteezy) images, multilingual chats (Hinglish/Spanish/Pinyin), multi-part claims, wrong-object/clean-part contradictions.

## The winning one-liner
**One multimodal agent, internally two-stage** (per-image perception → text-only adjudication), wrapped in a **deterministic decision tree + strict CSV formatter**. Treat **images as primary truth, conversation as the question, history + authenticity as parallel risk signals that never flip `claim_status` by themselves**. Ground every justification in cited image IDs. Ship a real `evaluation/` folder comparing ≥2 strategies with a cost/latency/rate-limit analysis. Keep an ownership-driven transcript. Rehearse the interview in "I chose / I rejected / I verified."

## The 5 highest-leverage edge moves
1. **Byte-level image normalization** (AVIF/WebP→PNG) — recover the ~8 silently-broken test rows competitors will miss.
2. **Two independent axes:** `valid_image` (trust/usable) ≠ `evidence_standard_met` (coverage), defended with case_008 (clear but watermarked).
3. **Mixed-determinism `risk_flags`:** `user_history_risk` + `manual_review_required` derived deterministically from CSV; visual flags from the VLM → wins the multi-label column.
4. **Injection defense as architecture:** transcribe-in-image-text-as-data + system boundary + critic echo-check; flag `text_instruction_present`, still judge on pixels (case_020 seal intact → contradicted).
5. **A genuinely rigorous `evaluation_report.md`:** real confusion matrix + ≥2-strategy comparison + measured ops/cost (~$0.85 full test; pre-resize -55% tokens, prompt-cache -90%).

## Hardest columns (where the score is won/lost)
`claim_status` (highest leverage; NEI-vs-contradicted boundary = "can I see the claimed part well enough to judge?") · `risk_flags` (multi-label F1) · `supporting_image_ids` (bare IDs, subset, `none`↔NEI coupling) · `issue_type` (`none` = visible-and-undamaged vs `unknown` = can't determine) · `severity` (calibrate to pixels, not the customer's adjectives).

## Recommended model plan (~$0.85 / full test set)
Stage-2 per-image perception → **Sonnet 4.6 / Gemini 3 Flash** (bulk, cached, parallel). Stage-3 adjudication → **Opus 4.8 text-only** (images distilled). ~7 hard rows re-checked with Opus + raw image. Temp 0, JSON-schema-forced output, image-hash cache, 8-way parallel + backoff retry.

## Immediate next steps (no code yet)
1. **You review the blueprint** (`research/05_winning_blueprint.md`).
2. **`/grill-me`** — resolve the [THIN] assumptions (June weights, output.csv stub, single-vs-two-stage framing, image-ID scoring strictness, provider/keys available).
3. **`/plan-eng-review`** — lock the Stage 0–6 architecture, `ClaimState` schema, validators, decision tree, eval harness.
4. Then, and only then, implement (time-boxed plan in blueprint §9; submittable `output.csv` by ~hour 6).
