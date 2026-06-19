# Accuracy-Improvement Research (papers, repos, techniques)

> Workflow wf_55481856-57a, 2026-06-19. Targeted at contradicted-recall, severity, risk_flags precision. All constrained to no-training / Claude-Code-only.


## THE IMPROVEMENT PLAN (Agent E - synthesis)

I have everything I need from the four research reports. This is a synthesis task, not a fresh research task, so I will fuse the findings into a concrete, prioritized plan against the codebase constraints. Let me also log this turn per the AGENTS.md contract, then deliver.

# Agent E: Concrete Improvement Plan for the Multi-Modal Evidence Review Pipeline

This fuses Agents A-D into one decisive, ranked plan under the hard constraints (Claude Code headless, no paid API, no training, ~20 labels, reproducible, hackathon time). The four reports **strongly converge** on one diagnosis: your contradicted-recall miss is the textbook VLM failure (visual entailment misclassifies *contradiction* as *neutral*; single-look / affirmative bias), and the fix is the same across all four: **a per-attribute, claim-blind adjudication step (S3) that feeds a deterministic comparator, never a holistic "does this match?" VLM call.** Your flag-precision and severity problems are *rule-discipline and rubric-anchoring* problems, not model problems.

---

## 1. RANKED IMPROVEMENT LIST (highest ROI first)

### #1 - Add S3 attribute-level adjudication + claim-blind S2 (contradicted-recall 2/5 → target 4-5/5)
- **Target metric:** contradicted-recall (primary), also lifts NEI quality and `supporting_image_ids` correctness.
- **Technique:** Visual-entailment decomposition + Chain-of-Verification (CoVe). Turn the claim into independent `verify(attribute)` sub-checks answered *draft-blind* against the image, then aggregate deterministically. The "different issue on a matching part = **contradiction**, not neutral" rule is the load-bearing change.
- **Sources:** SNLI-VE label definitions https://arxiv.org/abs/1901.06706 · VLM entailment pitfalls (misclassifies contradiction as neutral) https://arxiv.org/pdf/2507.17467 · IdealGPT decomposition https://arxiv.org/pdf/2305.14985 · VISTAR `verify()` schema https://arxiv.org/pdf/2505.08084 · CoVe (draft-blind verification) https://arxiv.org/abs/2309.11495 · CrossCheck single-look bias https://arxiv.org/pdf/2511.21717 · cross-modal visual-dominance fix https://arxiv.org/pdf/2507.01790
- **Exact codebase change:**
  - **S2 perception prompt:** make it strictly **claim-blind** (it must never see the claimed issue/severity). Ask the *open* form ("what damage, if any, is visible, and on which part?") not the leading form ("is there a dent on the door?"). Add explicit primitive definitions (`dent = concave deformation; scratch = surface line, no deformation`).
  - **New `code/agents/` adjudicator + new stage S3 between S2 and S4** (`pipeline.py`): one Claude call per claim that receives S1 claim attributes + S2 facts and emits per-attribute `{object, part, issue, severity} → match | mismatch/DIFFERENT_ISSUE | none_visible | unknown` plus the falsification answer.
  - **Decision tree (`code/domain/decision_tree.py`):** add the deterministic comparator branch: `part match AND (issue == DIFFERENT_ISSUE OR issue == none_visible) → contradicted`.
- **Accuracy impact:** High (the single biggest lever; directly targets the 2/5 → expected 4-5/5).
- **Effort:** M.

### #2 - Closed-vocabulary issue_type + few-shot anchors from the 20 labels (issue_type 0.75 →, severity 0.70 →)
- **Target metric:** issue_type, and (paired) severity.
- **Technique:** Constrain `issue_type` to a fixed CarDD-style vocabulary (forces selection from a closed set) and add 1-2 in-prompt anchor exemplars per class/tier from your labeled examples (ICL anchors fix Likert score-collapse and borderline cases).
- **Sources:** CarDD 6-class taxonomy https://cardd-ustc.github.io/ · INS-MMBench (type easy, severity hard; decompose) https://arxiv.org/pdf/2406.09105 · ICL grading demos https://arxiv.org/pdf/2603.00465 · Car-Damage-Assessment-AI 10-class + YAML decision-trace pattern https://github.com/artemxdata/Car-Damage-Assessment-AI · Parcel3D package taxonomy https://zenodo.org/records/8032204
- **Exact codebase change:** **S2 perception prompt** - inject the closed label list and 1-2 textual anchor descriptions per issue_type and per severity tier (pulled from `sample_support_tickets.csv`). Keep anchors as *visual-signature descriptions*, not raw labels of the test rows.
- **Accuracy impact:** Medium-high (cheapest single lever for both issue_type and severity).
- **Effort:** S.

### #3 - Risk_flags rule discipline (micro-F1 0.56 →): kill the two over-firing triggers
- **Target metric:** risk_flags micro-F1.
- **Technique:** Per-label thresholds + label-dependency/mutual-exclusion pruning + content-moderation "precision-floor" routing. Rare/costly flags need a HIGHER bar; micro-F1 is dominated by over-emitted common flags, so bias *against* emitting them.
- **Sources:** F1-optimal multi-label thresholding https://www.csie.ntu.edu.tw/~cjlin/papers/threshold.pdf · content-moderation precision-floor routing https://arxiv.org/pdf/2208.07522 · label-dependency pruning https://arxiv.org/html/2505.03118v1
- **Exact codebase change (`code/domain/decision_tree.py`):**
  - **Remove `if not valid_image: return True`** from `_should_require_manual_review` - a benign coverage gap must not auto-escalate (this contradicts your own domain invariant and is a prime false-positive source). Manual-review fires only on genuine trust triggers (`claim_mismatch`, `wrong_object`, `non_original_image`, `possible_manipulation`, `text_instruction_present`).
  - **Gate `user_history_risk`** so it surfaces only when the row is *also* `contradicted` or already carries another trust flag - never alone on a clean `supported` row.
  - **Mutual-exclusion pruning:** when `wrong_object` fires, drop part-level quality flags (`wrong_angle`, `blurry_image`); collapse to the decisive flag set.
- **Accuracy impact:** Medium-high (history + manual_review are named top over-flaggers; this is pure determinism, no model calls).
- **Effort:** S.

### #4 - Severity computed deterministically from S2 primitives + anchored rubric (severity 0.70 →)
- **Target metric:** severity accuracy.
- **Technique:** Don't trust a raw VLM severity *label* (empirically the model's weakest dimension). Have S2 emit observable primitives (`damage_extent` small/medium/large relative to part, functional cue: part intact/attached/detached, glass intact/shattered), then **S4 maps primitives → tier deterministically** against a locked, evidence-anchored rubric.
- **Sources:** INS-MMBench (severity hardest, decompose) https://arxiv.org/pdf/2406.09105 · CarDD area-based severity discretization https://cardd-ustc.github.io/ · RULERS locked rubric + evidence verification, no weight update https://arxiv.org/abs/2601.08654 · status→location→severity cascade https://link.springer.com/chapter/10.1007/978-3-032-06250-5_2
- **Exact codebase change:** S2 prompt emits `damage_extent` + functional cue; add a **severity rule** in `decision_tree.py` mapping `(issue_type, extent, functional_cue) → minor|moderate|severe`. Rubric: `minor = cosmetic/surface, functional; moderate = structural deformation, attached/functional; severe = detached/shattered/non-functional/safety`.
- **Accuracy impact:** Medium.
- **Effort:** M.

### #5 - Self-consistency vote on uncertain rows (issue_type, severity, contradicted)
- **Target metric:** issue_type, severity, contradicted-recall stability.
- **Technique:** Resample S2→S3→S4 k=5 at temperature and majority-vote each field; sample spread doubles as a confidence/abstention signal. **Only fire on uncertain rows** (first sample = contradicted/NEI or S3 disagreement) to stay in budget.
- **Sources:** Self-Consistency https://arxiv.org/abs/2203.11171 · self-consistency as confidence https://arxiv.org/pdf/2509.19489 · CoT-overconfidence → use agreement not self-reported confidence https://arxiv.org/html/2603.16728v1
- **Exact codebase change:** `pipeline.py` - wrap S2-S4 in a k-sample majority-vote for flagged-uncertain rows; fixed seed/sample count for reproducibility.
- **Accuracy impact:** Medium (well-evidenced, but extra calls).
- **Effort:** M.

### #6 - Authenticity signal hardening + pHash threshold fix (valid_image / manipulation precision)
- **Target metric:** `valid_image`, `non_original_image`/`possible_manipulation` precision (feeds risk_flags).
- **Technique:** Add classical ELA (JPEG-only, strong-localized-anomaly only) + JPEG quantization-table read; **lower `RECYCLED_HAMMING_THRESHOLD` 6 → 4-5** (6 is loose, inflates false matches); **demote missing-EXIF to a very weak prior** (honest screenshots/chat re-uploads strip EXIF). Keep watermark/stock/AI-gen detection in the Claude vision `authenticity` field, not classical code.
- **Sources:** Sherloq/ELA https://github.com/GuidoBartoli/sherloq · double-JPEG https://arxiv.org/pdf/2003.09393 · ImageHash threshold distributions https://www.sciencedirect.com/science/article/pii/S2666281723000100 · C2PA positive-only signal https://opensource.contentauthenticity.org/docs/c2pa-python/
- **Exact codebase change (`code/images/authenticity.py`):** lower the Hamming threshold (one line, do this first); add ELA + quantization-table as *weak* contributors gated to strong anomalies; demote `has_camera_exif == False`.
- **Accuracy impact:** Low-medium (the threshold one-liner is the high-ROI piece).
- **Effort:** S (threshold) / M (ELA).

### #7 - Cross-model disagreement gate for "confident-but-wrong" NEI (optional, if budget allows)
- **Target metric:** NEI accuracy on confident-but-wrong rows.
- **Technique:** Get the verdict from two *genuinely different reasoning paths* (e.g., Sonnet-with-CoVe vs Opus-single-shot); agreement → accept, disagreement → NEI/escalate. Self-consistency collapses on confident-wrong cases; cross-model disagreement catches exactly those. Do NOT fake a panel with one model family (correlated errors → ~2 effective votes).
- **Sources:** Trust-or-Escalate cascade (ICLR'25 oral) https://arxiv.org/abs/2407.18370 · cross-model disagreement UQ https://arxiv.org/abs/2604.17112 · "Nine Judges, Two Effective Votes" https://arxiv.org/abs/2605.29800
- **Effort:** M. **Defer unless #1-#4 land with time to spare.**

---

## 2. S3 ADJUDICATION DESIGN (the contradicted-recall fix)

**Goal:** stop the model from rationalizing claim+image into agreement. Achieved by *separating perception (S2, claim-blind) from adjudication (S3, reasons over discrete facts, never re-judges the raw image holistically)* and *aggregating deterministically*.

**Call count: ONE Claude call per claim** (not per image; S2 already did per-image perception). Optionally 0 extra calls if you make S3 a pure deterministic comparator over S2 facts - but one LLM call buys you the falsification reasoning and `justification` text for the judge interview round. Keep it to one for hackathon budget.

**Prompt structure (per-attribute verify → falsification → emit; aggregation is OUTSIDE the LLM):**

```
You are adjudicating ONE claim against the objective image facts already extracted.
You do NOT see the raw images. Judge each attribute INDEPENDENTLY. Do not assume the
inputs are consistent.

CLAIM (from S1):  object=<>, part=<>, issue_type=<>, severity=<>
IMAGE FACTS (S2, claim-blind): shown_object, shown_part, has_visible_damage,
  issue_guess, severity_guess, quality_issues, authenticity, per image_id

For each attribute output one token:
1. OBJECT:   shown_object vs claim.object       -> match | mismatch | unknown
2. PART:     shown_part   vs claim.part         -> match | mismatch | unknown
3. ISSUE:    issue_guess  vs claim.issue_type   -> match | DIFFERENT_ISSUE | none_visible | unknown
4. SEVERITY: severity_guess vs claim.severity   -> match | mismatch | unknown

FALSIFICATION (required): "What in the image facts would prove the claim FALSE?"
  A different issue on the matching part, or no damage on a part claimed damaged,
  is CONTRADICTION (not insufficient evidence).

For ISSUE/SEVERITY, cite the supporting image_id.
Return JSON only. Do NOT output a final verdict — the system computes it.
```

**Deterministic aggregation (in `decision_tree.py`, NOT in the LLM):**
```
if any(quality_issues blocks the deciding attribute) and no clear signal:  not_enough_information
elif ISSUE == DIFFERENT_ISSUE  OR (PART == match AND ISSUE == none_visible): contradicted
elif OBJECT == mismatch:                                                     contradicted (wrong_object)
elif OBJECT,PART,ISSUE all == match AND has_visible_damage AND grounded id:  supported
else:                                                                        not_enough_information
```
- **Why it works:** the contradiction branch fires on `part match + different/absent issue` - the exact case you miss today. The FEVER-style evidence gate (https://arxiv.org/abs/1803.05355) requires a concrete `supporting_image_id` before `supported`/`contradicted`; no pointer → NEI. This both fixes contradicted-recall and *populates `supporting_image_ids` for free*.

**How it combines with the tree:** S3 is advisory perception-comparison; the **tree is authoritative** (matches the "LLM advisory, rules authoritative" reproducibility posture). The tree owns every status flip and every flag.

**LOOCV validation on 20 labels without overfitting (use existing `code/evaluation/cross_validation.py`):**
1. The 20 labels are a *calibration/validation* set, never training data baked into prompts. Keep few-shot anchors (#2) drawn from a **fixed held-out subset** and *exclude that subset's rows from the LOOCV folds* so anchors never leak into their own evaluation.
2. Run **leave-one-out**: for each of 20, predict with the other 19's context, score the held-out one. Report contradicted-recall + per-column accuracy across all 20 folds.
3. Tune only **discrete knobs** (the aggregation rule branches, the flag-gating rules, the Hamming threshold) by LOOCV micro-F1 - not free-form prompt tweaking. Limit yourself to a handful of config variants to avoid overfitting 20 points.
4. **Conformal NEI threshold** (https://arxiv.org/abs/2405.01563): with 20 points as a conformal calibration set, pick the self-consistency-agreement cutoff for flipping to NEI so the verdict-error rate on non-abstained rows is bounded (~≤10%). 20 points is enough for a single conformal quantile (not for fine-tuning).

---

## 3. RISK_FLAGS PRECISION + SEVERITY CALIBRATION (concrete)

**Risk_flags (micro-F1 0.56):**
- **Remove `if not valid_image: return True`** in `_should_require_manual_review` - benign coverage gap must not escalate (your own invariant). Source: content-moderation precision-floor https://arxiv.org/pdf/2208.07522.
- **`user_history_risk` only alongside another trust flag / contradicted** - never alone on a clean supported row; history never flips status. Source: label-dependency pruning https://arxiv.org/html/2505.03118v1.
- **Mutual exclusion:** `wrong_object` ⇒ drop part-level quality flags; don't stack redundant quality flags once decided. Source: F1-optimal thresholding https://www.csie.ntu.edu.tw/~cjlin/papers/threshold.pdf.
- **Rare/costly flags require a higher bar** than common quality flags; micro-F1 is dominated by over-emitted common flags so bias against emitting them. Tune the final rule config by LOOCV.

**Severity (0.70):**
- Replace VLM severity-label with **S2 observable primitives** (`damage_extent`, functional cue, glass intact/shattered), compute tier in S4 against a **locked anchored rubric** with evidence citation. Sources: RULERS https://arxiv.org/abs/2601.08654, INS-MMBench (severity is the weakest VLM dimension) https://arxiv.org/pdf/2406.09105, CarDD area-based discretization https://cardd-ustc.github.io/.
- Add **1-2 anchor exemplars per tier** in the prompt to stop Likert score-collapse on borderline rows. Source: https://arxiv.org/pdf/2603.00465.

---

## 4. WHAT TO AVOID

- **No introspective "are you sure?" / self-refine critic** on the existing verdict with no new evidence - it *lowers* accuracy (sycophantic flipping). Any critic must consume a NEW signal (fresh image read, second model, atomic check). Sources: https://arxiv.org/abs/2310.01798, https://arxiv.org/abs/2311.08596.
- **No fine-tuning / no learned forgery models** (TruFor/Noiseprint++ need PyTorch weights + GPU, not Claude-headless-callable). Source: https://grip-unina.github.io/TruFor/.
- **No standalone AI-generated-image detector** - <80% cross-dataset, false-positives on legitimately edited honest claim photos; would crater your already-low flag precision. Route any AI-gen signal softly through the vision `authenticity` field. Sources: https://arxiv.org/pdf/2502.15176, https://arxiv.org/pdf/2602.07814.
- **No holistic "does this image match the claim?" single VLM call** - it defaults to agreement (visual dominance / single-look bias) and misclassifies contradiction as neutral. Sources: https://arxiv.org/pdf/2507.01790, https://arxiv.org/pdf/2507.17467, https://arxiv.org/pdf/2511.21717.
- **No verbalized-confidence thresholding** for NEI - it's overconfident and decoupled from the answer. Use sample-agreement / evidence-coverage gates instead. Sources: https://arxiv.org/abs/2601.07767, https://arxiv.org/abs/2604.01457.
- **No fake multi-Claude "panel"** for abstention - correlated errors yield ~2 effective votes; the best single judge matches the panel. Source: https://arxiv.org/abs/2605.29800.
- **No copy-move forensics / full multi-round debate** - low ROI for 24h.

---

## 5. IF I ONLY HAD 2 HOURS

- **Add S3 attribute-level adjudication with the falsification prompt + the deterministic `part-match + different/absent-issue → contradicted` branch in `decision_tree.py`, and make S2 claim-blind/open-ended.** This is the contradicted-recall fix (the biggest miss). (~1 hr)
- **Decision-tree flag discipline (pure determinism, zero model calls):** remove `if not valid_image: return True`, gate `user_history_risk` to fire only with another trust flag, add `wrong_object` mutual-exclusion pruning. Biggest risk_flags micro-F1 gain for the least effort. (~30 min)
- **Two cheap config wins:** lower `RECYCLED_HAMMING_THRESHOLD` 6→4 in `images/authenticity.py`, and inject the closed `issue_type` vocabulary + 1-2 severity anchor exemplars into the S2 prompt. (~30 min)

Relevant files: `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/code/agents/` (new adjudicator), `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/code/pipeline.py` (wire S3), `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/code/domain/decision_tree.py` (comparator + flag rules + severity rule), `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/code/images/authenticity.py` (Hamming threshold + ELA), `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/code/evaluation/cross_validation.py` (LOOCV tuning).

---

## VLM Damage Assessment & Insurance (Agent A)

I have comprehensive, well-cited coverage across all four sub-areas with mechanisms that map directly to the system's weak spots. Compiling the final report.

---

# Agent A Report: VLM Damage Assessment & Insurance Claim Verification

Research mapped to the Multi-Modal Evidence Review pipeline (S1 extract, S2 perception, S4 decision tree, S6 CSV). Every recommendation below is feasible with **no training, no paid API** - it is prompting, in-context exemplars, deterministic rules, or light classical CV. Training-only sources are flagged.

---

## 1. Damage taxonomies & severity rubrics (maps to S2 facts + S4 severity rule)

### CarDD - the reference taxonomy
- **URL:** https://cardd-ustc.github.io/ | paper https://ar5iv.labs.arxiv.org/html/2211.00945 | roboflow mirror https://universe.roboflow.com/car-damage-detection-cardd/car-damage-severity-detection-cardd
- **Technique:** First large public car-damage dataset (4,000 images, 9,000+ instances). Uses a **6-class fine-grained damage taxonomy: dent, scratch, crack, glass shatter, lamp broken, tire flat**. Critically, it discretizes severity by **instance area** (small <128², medium 128²-256², large ≥256² px) and ships per-image metadata for instance count, category, severity, and shooting angle.
- **Maps to our pipeline:** Adopt CarDD's 6 labels verbatim as the closed `issue_type` vocabulary in the S2 prompt (forces the VLM to pick from a fixed set, raising the 0.75 issue_type accuracy). The **area-based severity discretization is the most borrowable idea**: have S2 return a coarse `damage_extent` (small/medium/large relative to the part) and let the deterministic S4 rule map extent + issue_type -> severity, instead of asking the VLM to name "minor/moderate/severe" directly (VLMs are weak at the absolute severity label - see INS-MMBench below). **Feasible without training** (taxonomy + rubric only; the labeled dataset requires a license form but you do not need it to borrow the schema).

### INS-MMBench - LVLM insurance benchmark (the single most on-point academic source)
- **URL:** https://arxiv.org/pdf/2406.09105
- **Technique:** A benchmark evaluating LVLMs (GPT-4V, Gemini) on insurance vision tasks including vehicle damage type, **severity**, and part localization. Two findings matter: (a) **severity assessment is markedly harder than type classification** for VLMs - they handle "what kind of damage" far better than "how bad," and part localization is weakest; (b) **task decomposition helps** - asking type, then severity, then location as separate focused sub-questions beats one combined question.
- **Maps to our pipeline:** This is direct empirical justification for our staged S2 -> S4 split, and it tells us *where* to spend effort. Because severity is the model's weakest dimension, **do not trust a raw VLM severity label** - have S2 emit observable primitives (extent, depth cue, is-the-part-still-functional, glass-intact-vs-shattered) and compute severity deterministically in S4. This directly attacks our severity-accuracy 0.70 weak spot.

### Vehicle Damage Severity in-the-wild + hybrid status/location/severity
- **URLs:** https://www.researchgate.net/publication/372667360 (in-the-wild mobile, 403 on fetch but abstract confirms minor/moderate/severe tiering + explicit blur/lighting/angle handling) | https://link.springer.com/chapter/10.1007/978-3-032-06250-5_2 (hybrid status->location->severity pipeline) | survey https://ieeexplore.ieee.org/document/11142438/
- **Technique:** These split the problem into **status (damaged y/n) -> location (which part) -> severity (3 tiers)** as a cascade, and the in-the-wild paper explicitly models mobile-image quality issues (blur, lighting, angle) as a gating factor before estimating severity.
- **Maps to our pipeline:** Validates our S2 `quality_issues` and `valid_image` fields as a **gate that must run before** severity/verdict, and mirrors our staged decomposition. The cascade ordering (quality gate -> object/part -> damage -> severity) is a clean template for S4 rule ordering.

---

## 2. The contradicted-recall problem (weak spot #1 - this is the highest-value finding)

Our biggest gap (2/5 contradicted-recall: image shows a *different* issue than claimed) is a **known, named failure mode** of VLMs, with published, training-free fixes.

### Cross-modal conflict / visual dominance
- **URL:** https://arxiv.org/pdf/2507.01790 ("How Do Vision-Language Models Process Conflicting Information Across Modalities?")
- **Technique:** VLMs have a systematic **visual-dominance / affirmative bias** - when image and text disagree they silently default to one modality and *assume the inputs are consistent* rather than reporting the conflict. The key training-free fix: **explicit prompting that directly instructs the model to identify contradictions between modalities significantly improves conflict detection.**
- **Maps to our pipeline:** This is the fix for contradicted-recall. Our S2 must be **claim-blind** (already good - it returns objective facts), and S4 must then do an **explicit field-by-field comparison**: claimed_issue_type vs shown issue (e.g. claim="dent" but S2 facts say has_visible_damage=true + issue_guess="scratch" + same part) -> `claim_status = contradicted`. Do not let any single call see both "claim" and "image" and emit a verdict - it will rationalize them into agreement. Make the contradiction check a deterministic comparator in S4, not a VLM judgment.

### Affirmative bias / "what not to detect" (negation-aware)
- **URL:** https://openreview.net/pdf/b8147865b8a0612c44c09bb64da45025461a41f1.pdf
- **Technique:** Standard VLMs have an **affirmative bias** - they fail to correctly answer contradictory/negation queries ("is there a dent?" tends toward "yes"). 
- **Maps to our pipeline:** Avoid leading questions in S2. Instead of "is there a dent on the door?" (primes a yes), ask the **open** form "what type of damage, if any, is visible and on which part?" then compare in S4. This single prompt-shape change should lift contradicted-recall and reduce false-supported.

### Multi-agent cross-modal consistency validators (the architectural pattern)
- **URLs:** https://arxiv.org/pdf/2508.06623 (ContextGuard-LVLM) | https://arxiv.org/pdf/2507.09174 (RAMA) | https://arxiv.org/pdf/2505.15489 (misleading intent)
- **Technique:** These fact-checking frameworks add a dedicated **image-text mismatch detector** as a separate component that emits a binary consistency decision across three axes: image manipulation, text distortion, and **semantic image-text mismatch**. Separating the consistency judge from the perception step reduces single-model bias.
- **Maps to our pipeline:** Conceptually our S4 *is* the consistency validator - this literature says make that role explicit and decompose the mismatch check into the same axes we already track (authenticity ≈ manipulation, embedded_text/claim ≈ text distortion, issue/part mismatch ≈ semantic mismatch). No extra model needed; it is a structured comparison.

---

## 3. Severity calibration without training (weak spot #3, severity 0.70)

### RULERS - locked rubrics + evidence-anchored scoring
- **URL:** https://arxiv.org/abs/2601.08654
- **Technique:** Compiles a natural-language rubric into an executable spec, enforces **structured decoding with deterministic evidence verification**, and applies lightweight post-hoc calibration - **without updating model weights.**
- **Maps to our pipeline:** This is the blueprint for our S2 severity rubric. Write an **anchored rubric** (e.g. "minor = cosmetic, paint/surface only, part fully functional; moderate = structural deformation but part attached/functional; severe = part detached/shattered/non-functional or safety-relevant") and require S2 to **cite the visual evidence** for the tier it picks. Then S4 verifies the tier against the cited evidence deterministically. Fully training-free.

### In-context demonstrations + anchored Likert (fix score-collapse)
- **URLs:** https://arxiv.org/pdf/2603.00465 (optimizing ICL demos for grading) | https://www.twine.net/blog/llm-evaluation-rubrics/ | https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-...-71936b989e80
- **Technique:** A Likert rubric **without exemplars collapses toward central scores** because the judge has no shared mental image of each scale point. Pairing the rubric with a few **labeled anchor exemplars** per tier gives robust gains, especially on **borderline cases** - exactly our error region.
- **Maps to our pipeline:** We have ~20 labeled examples - too few to fine-tune but **perfect as in-prompt severity anchors.** Put 1-2 reference examples per severity tier (description of the visual signature, not necessarily the image) into the S2 prompt as few-shot anchors. This is the single cheapest lever for severity 0.70 -> higher, and it doubles as issue_type anchors (0.75).

---

## 4. Over-flagging risk_flags (weak spot #2, micro-F1 0.56) + abstention quality

### CoT induces overconfidence; use agreement-based consistency
- **URL:** https://arxiv.org/html/2603.16728v1 ("The Cost of Reasoning")
- **Technique:** Chain-of-thought **improves accuracy but degrades uncertainty/calibration** in VLMs via "implicit answer conditioning" - token probabilities reflect commitment to the reasoning trace, not real confidence. Recommended alternative for calibrated/abstaining outputs: **agreement-based consistency (sample multiple answers, majority-vote, use disagreement as the abstain signal).**
- **Maps to our pipeline:** Two concrete actions. (a) For the `not_enough_information` verdict and `valid_image` gate, **do not rely on the VLM's self-reported confidence** - use multi-sample agreement: run S2 perception 3x at temp>0, and if the issue_type/part disagree across samples, route to `not_enough_information` / set a quality flag. This is deterministic-ish (fixed seed/sample count) and reproducible. (b) For risk_flags over-flagging: make each flag fire from an **explicit deterministic rule in S4** (e.g. manual_review fires only if quality_issue OR authenticity<threshold OR contradiction), never as a free-form VLM multi-label guess. Precision problems on multi-label almost always come from letting the model emit the labels; gate them on observable facts.

### Selective prediction / abstention literature
- **URLs:** https://arxiv.org/pdf/2505.09591 (uncertainty-aware selective VQA) | https://openaccess.thecvf.com/content/CVPR2024/papers/Khan_Consistency_and_Uncertainty_...CVPR_2024_paper.pdf | https://arxiv.org/pdf/2402.00367 (abstain via multi-LLM collaboration)
- **Technique:** Reliability = **consistency across semantically-equivalent rephrasings**; a response that flips under paraphrase is unreliable -> abstain. Multi-LLM/multi-sample collaboration identifies knowledge gaps better than single-pass confidence.
- **Maps to our pipeline:** Implement `not_enough_information` as a **consistency gate**: ask the S2 question two ways (open + targeted) and if facts disagree, abstain. Directly improves both contradicted-recall (catches ambiguous cases) and avoids false-supported.

---

## 5. Open-source repos to borrow architecture/prompts from

### Car-Damage-Assessment-AI (closest architectural twin to our pipeline)
- **URL:** https://github.com/artemxdata/Car-Damage-Assessment-AI
- **Technique:** Exactly our shape - **CV perception (YOLOv8, 10 CarDD-derived classes: crack, crash, dent, dislocated part, glass shatter, lamp broken, no part, rub, scratch, tire flat) -> deterministic YAML policy rules with explicit thresholds -> optional non-authoritative LLM guidance.** Outputs `AUTO_APPROVE | HUMAN_REVIEW | ESCALATE` with a **traceable decision trace naming which rule fired**. "Deterministic by default; every decision produces a traceable explanation."
- **Maps to our pipeline:** Borrow the **YAML-policy + decision-trace pattern for S4** and the **10-class taxonomy** (richer than CarDD's 6 - adds rub, dislocated part, no part - useful for our object_part / risk_flags). The "LLM is advisory, rules are authoritative" stance is exactly the right reproducibility posture for the hackathon. Borrow prompt/rule structure; ignore the YOLO training part.

### Other repos (taxonomy + part-localization ideas, all training-based - borrow schema only)
- https://github.com/topics/car-damage-detection and https://github.com/topics/car-damage-detector (topic hubs)
- https://github.com/louisyuzhe/car-damage-detector and https://github.com/basel-ay/Automated-Car-Damage-Detection (Mask R-CNN damage-region segmentation)
- https://github.com/megha070/Claim-It-Up-1 (motor-claim *verification* flow: cross-checks policyholder/vehicle details + cost estimate - a verification-flow template, closest to our "verify the claim" framing)
- A common 4-submodel decomposition appears repeatedly: **is-it-a-car -> is-it-damaged -> which-part -> severity** - reuse this as the S4 rule ordering.

### Package / device damage (for the non-car claim types)
- **Parcel3D** (synthetic, 13k+ images, damaged vs intact, 2D+3D COCO annotations): https://zenodo.org/records/8032204 - schema for package damage states.
- **Damaged Package Detection** (Roboflow, ~1,000 images, damaged/intact): https://universe.roboflow.com/iot-project/damaged-package-detection
- **Technique/maps to us:** These give the **package-damage taxonomy** (crushed/torn/dented/wet/open vs intact) to populate our `issue_type` vocabulary for package claims, and confirm a simple **intact-vs-damaged binary as the first gate** before issue typing. Device/laptop screen-crack: covered in passing by the same VGG16/YOLO crack-classification literature (screen crack -> our "glass shatter"/"crack" analog) - no clean public device-damage benchmark surfaced; reuse CarDD's crack/glass-shatter visual cues.

---

## 6. Industry / insurtech structure (FNOL automation)
- **URLs:** https://binariks.com/blog/ai-car-damage-detection/ | https://newgensoft.com/resources/article/fnol-automation-and-agentic-ai-.../ | https://www.altexsoft.com/blog/automated-claims-processing/ | https://acquaintsoft.com/blog/insurance-claims-automation
- **Technique:** Leading FNOL pipelines structure output as **damage type + severity tier + part localization + a triage routing decision** (straight-through-process / auto-approve vs adjuster review vs escalate), and apply **severity+type triage rules** to route claims. LLMs extract entities from the narrative; image recognition validates the reported loss against the photo.
- **Maps to our pipeline:** Validates our exact output schema (claim_status + issue_type + object_part + severity + a review/escalate flag). The industry "validate reported loss against photo" step is precisely our contradicted-detection job - confirms it is the high-value differentiator. The STP/auto-approve-vs-review split maps onto our `evidence_standard_met` + `risk_flags(manual_review)`.

---

## Bottom line - ranked, training-free actions by weak spot

1. **Contradicted-recall (2/5):** Keep S2 claim-blind and ask **open** ("what damage, if any, and where") not leading questions (counters affirmative bias, arxiv 2507.01790 + negation paper). Do the claim-vs-fact mismatch as an **explicit deterministic comparator in S4**, never inside a VLM call that sees both. *Highest ROI.*
2. **Severity (0.70):** Replace VLM severity-label with **observable primitives + anchored rubric** (RULERS 2601.08654) and add **1-2 in-prompt anchor exemplars per tier** from your 20 labeled examples (ICL-demos paper 2603.00465). Compute the final tier in S4 from CarDD-style extent + functional cues.
3. **issue_type (0.75):** Constrain to a **closed CarDD/10-class vocabulary** + few-shot anchors.
4. **risk_flags micro-F1 (0.56):** Fire each flag from an **explicit S4 rule gated on facts**, not VLM free-form multi-label. Use **multi-sample agreement** (CoT-overconfidence paper 2603.16728) for the `not_enough_information` and `valid_image` gates instead of self-reported confidence.

No source above requires fine-tuning, GPUs, or a paid API to apply the recommended techniques - all are prompt-shape, in-context-exemplar, deterministic-rule, or multi-sample-consistency changes compatible with Claude Code headless and reproducible runs.

---

## Visual Claim-Evidence Consistency (Agent B)

I have everything needed to write the report. The canonical contradiction-vs-neutral definition is well established in the literature (entailment = image makes claim certainly true; neutral = image neither confirms nor denies, i.e. insufficient evidence; contradiction = image makes claim false). This maps directly to your three classes. Here is the final research report.

---

# Agent B Report: Visual Claim-Evidence Consistency (Contradicted-Recall)

The single highest-leverage finding: your failure mode is **textbook**. The visual-entailment literature documents exactly your bug - VLMs systematically misclassify **contradiction as neutral** (they conflate "image shows a different issue" with "image is inconclusive"). The fix is also documented: do **not** let one VLM call holistically judge support/contradict/insufficient. Instead **decompose into per-attribute sub-checks, answer each against the image independently, then aggregate with a deterministic rule** - which is exactly the S3 adjudication step you're missing between S2 (per-image facts) and S4 (decision tree).

---

## 1. Task framing: Visual Entailment = your exact 3-class problem

### Visual Entailment: A Novel Task for Fine-Grained Image Understanding (SNLI-VE)
**URL:** https://arxiv.org/abs/1901.06706 · code: https://github.com/necla-ml/SNLI-VE

**Core technique (2-3 sentences):** Defines the Visual Entailment task: given an image *premise* and a text *hypothesis*, predict one of three labels. The canonical label definitions are: **entailment** = there is enough evidence in the image to conclude the hypothesis is **true**; **contradiction** = there is enough evidence to conclude it is **false**; **neutral** = the image does not give enough evidence to decide either way.

**Maps to your pipeline:** This is a 1:1 mapping. `image premise + claim text` → `{entailment, contradiction, neutral}` is identical to your `{supported, contradicted, not_enough_information}`. Adopt the *exact* label criteria: the line "**enough evidence to conclude the claim is false**" is precisely what your S4 must require before emitting `contradicted` - and critically, "different issue than claimed, same part" (dent claimed, scratch shown) **is** a contradiction under this definition, because the image affirmatively shows the claimed defect is absent. Your current system is treating it as neutral because it only checks "is the part visible / is there damage," not "is the *claimed* issue present vs a *different* issue present."

### Probing Vision-Language Understanding through the Visual Entailment Task: promises and pitfalls (2025)
**URL:** https://arxiv.org/pdf/2507.17467

**Core technique:** Empirically studies zero-shot VLM performance on visual entailment. Finds VLMs have a **specific, severe weakness on contradiction**: they "frequently misclassify contradictory statements as neutral," exhibit **label bias**, and do "surface-level pattern matching rather than genuine logical inference about negation and incompatibility." Explicit, category-defining prompts beat ambiguous ones.

**Maps to your pipeline:** This paper *is* your bug report. Two direct takeaways: (a) never use a vague prompt like "does this image match the claim?" - instead give the model the explicit contradiction criterion ("contradiction = the image shows the claimed issue is NOT what is present, e.g. a different defect type"); (b) because the neutral→contradiction confusion is a known VLM failure, do not trust a single holistic judgment - force the attribute-level decomposition in §3. This justifies the entire S3 design.

---

## 2. The fix pattern: decompose → check each attribute → aggregate

This is the core architecture you should add. Four converging sources:

### IdealGPT: Iteratively Decomposing Vision and Language Reasoning via LLMs
**URL:** https://arxiv.org/pdf/2305.14985

**Core technique:** A three-stage loop: (1) an LLM generates targeted sub-questions about the image relevant to the claim ("Does the image contain X?", "What is the relationship between A and B?"); (2) a VQA/vision model answers each sub-question **against the actual pixels**; (3) the LLM synthesizes the answers into a verdict (entailment/contradiction/neutral). Iterates until confident.

**Maps to your pipeline:** This is the blueprint for **S3 adjudication**. Your S2 already produces per-image objective facts - treat those facts (plus targeted follow-up vision calls) as the "VQA answers," then run a reasoning step that compares each fact to the corresponding claim attribute and outputs the verdict. The key insight you're missing: **the entity that judges support/contradict should reason over discrete extracted facts, not look at the image and the claim together** (which lets the language prior win).

### VISTAR / Subtask-of-Thought reasoning (CVPRW 2025)
**URL:** https://arxiv.org/html/2505.08084 · PDF: https://arxiv.org/pdf/2505.08084

**Core technique:** Decomposes a visual query into a typed operation sequence with intermediate results: `select(object)`, `filter(objects, attribute)`, `verify(object, attribute)→bool`, `query(object, attribute)→value`, `relate(subj, rel, obj)`. Each step yields a `{textual_answer, bounding_box}`, making reasoning auditable. The `verify(object, attribute)→boolean` operation is exactly a per-attribute consistency check.

**Maps to your pipeline:** Gives you the **schema** for S3. Turn the claim into a fixed set of `verify(...)` operations, one per attribute:
- `verify(object == claimed_object)` → e.g. is it actually a laptop?
- `verify(part == claimed_part)` → is the screen the damaged part?
- `verify(issue_type == claimed_issue)` → **this is the one catching your dent-vs-scratch miss**
- `verify(severity ~= claimed_severity)`

Each returns true / false / unknown. This typed, per-attribute structure is what turns "the part matches so I'll say supported/neutral" into "part matches BUT issue_type verify=false → **contradicted**."

### Visual Question Decomposition on Multimodal LLMs (2024)
**URL:** https://arxiv.org/pdf/2409.19339 · related: https://arxiv.org/pdf/2308.09970 (Inner Monologue for VE)

**Core technique:** Studies how to make MLLMs decompose a question into good sub-questions, and confirms decomposition + answering sub-questions improves compositional reasoning over end-to-end answering. Pairs with the "inner monologue" approach shown to help specifically on SNLI-VE.

**Maps to your pipeline:** Reinforces that S3 should explicitly emit the sub-question list and per-sub-question answers (store them as `justification`), not a single verdict token. The audit trail also improves your `justification` column quality for the AI judge interview round.

### Concrete S3 prompting pattern (synthesized from the above)

The exact pattern to wire in, run **after** S2 facts exist, as a separate deterministic-where-possible step:

```
You are adjudicating ONE image against ONE claim. You are given:
- CLAIM ATTRIBUTES (parsed in S1): object=<>, part=<>, issue_type=<>, severity=<>
- OBJECTIVE IMAGE FACTS (from S2 perception): shown_object=<>, shown_part=<>,
  has_visible_damage=<>, issue_guess=<>, severity_guess=<>, quality_issues=<>

Do NOT look at the claim text as a whole. Judge each attribute independently:

1. OBJECT match?   shown_object vs claim.object        -> match | mismatch | unknown
2. PART match?     shown_part vs claim.part            -> match | mismatch | unknown
3. ISSUE match?    issue_guess vs claim.issue_type     -> match | DIFFERENT_ISSUE | none_visible | unknown
4. SEVERITY match? severity_guess vs claim.severity    -> match | mismatch | unknown

Then ask the falsification question explicitly:
"What in this image would prove the claim FALSE?" If the image clearly shows a
DIFFERENT issue on the matching part, or NO damage on a part claimed damaged,
that is CONTRADICTION, not neutral.

AGGREGATE (deterministic):
- any attribute == DIFFERENT_ISSUE or (part match AND issue none_visible)  -> contradicted
- all relevant attributes == match AND has_visible_damage                  -> supported
- otherwise (unknowns, quality_issues block judgment)                      -> not_enough_information
```

The **"what would prove the claim false?"** falsification prompt is the single most important line - it directly counteracts the documented agree-with-the-claim bias.

---

## 3. Stopping the model from agreeing with claims the pixels don't show

### HallusionBench: diagnostic suite for language-hallucination & visual illusion
**URL:** https://arxiv.org/pdf/2310.14566

**Core technique:** Pairs each yes/no question with a control vs manipulated image; when a VLM gives the same answer despite the visual change, it proves the **language prior overrode the pixels**. The consistency check (same answer across visually contradictory inputs = hallucination) is the detection mechanism.

**Maps to your pipeline:** Two uses. (a) **Evaluation:** build a tiny contrast set from your ~20 labeled examples - for a "dent" claim, also probe "is there a scratch?" and "is there a dent?"; a faithful pipeline must answer these differently. (b) **Inference-time guard:** ask the issue question *neutrally* ("what type of damage is visible?") **before** ever showing the claim, so the claim text can't anchor the answer. This neutral-first ordering is the cheapest, highest-impact prompt change for contradicted-recall.

### Counterfactual / contrastive hallucination mitigation (training-free)
**URLs:** CounterfactualLVLM https://www.researchgate.net/publication/401147486 · CounterVQA https://arxiv.org/html/2511.19923v1 · HalluSegBench https://arxiv.org/html/2506.21546v1 · Awesome-LVLM-Hallucination (curated list) https://github.com/NishilBalar/Awesome-LVLM-Hallucination

**Core technique:** Training-free, plug-and-play contrastive reasoning: explicitly contrast the model's behavior when a salient object/region is present vs removed, or pose counterfactual ("what would falsify this?") questions, to expose claims grounded in priors rather than pixels.

**Maps to your pipeline:** Adds the **contrastive question** to S3: for each claimed attribute, ask both "evidence the claim is TRUE?" and "evidence the claim is FALSE?" in the same call and require the model to weigh them. If the falsifying evidence (different issue visible) is stronger, emit `contradicted`. No training, no GPU - pure inference-time prompting, fits the hackathon constraints. The Awesome-LVLM-Hallucination repo is your menu of further training-free methods.

### Seeing is Believing: backward visual grounding for hallucination detection (2025)
**URL:** https://arxiv.org/pdf/2511.12140 (related claim-decomposition: https://arxiv.org/pdf/2503.20504)

**Core technique:** Segment a generated response into **atomic claims**, then verify each by "looking back" at the image as an independent VQA query - each atomic claim becomes its own grounded yes/no check.

**Maps to your pipeline:** Confirms the atomic-claim-verification design and gives you the **valid_image / evidence_standard_met** logic: a verdict only counts as `supported`/`contradicted` if its supporting atomic claim was grounded back to a specific image region; otherwise it falls to `not_enough_information`. This is your principled abstention rule.

---

## 4. Evidence-sufficiency & the not_enough_information class (abstention/calibration)

### FEVER: Fact Extraction and VERification
**URL:** https://arxiv.org/abs/1803.05355 · ACL: https://aclanthology.org/N18-1074/ · code: https://github.com/awslabs/fever

**Core technique:** The original {Supported, Refuted, NotEnoughInfo} framework. Crucially, a verdict of Supported/Refuted **requires the annotator to record the specific evidence sentence(s)**; if no sufficient evidence set exists, the label is forced to NotEnoughInfo.

**Maps to your pipeline:** This gives you a **hard gate for abstention**: S4 may only emit `supported` or `contradicted` if S3 produced a concrete supporting fact (a specific `supporting_image_id` + the attribute facts that decided it). No evidence pointer → `not_enough_information`. This both improves your NEI handling and **populates `supporting_image_ids` correctly** as a byproduct. It also reduces over-confident `contradicted`/`supported` calls that hurt precision.

### MOCHEG: End-to-End Multimodal Fact-Checking (the image version of FEVER)
**URL:** https://arxiv.org/pdf/2205.12487 · ACM: https://dl.acm.org/doi/abs/10.1145/3539618.3591879

**Core technique:** Multimodal claim verification predicting {Supported, Refuted, NEI} from **image + text evidence**, with an explicit evidence-retrieval stage feeding the verdict stage. Separates "which evidence is relevant" from "what is the verdict."

**Maps to your pipeline:** Validates your staged architecture (retrieve/extract evidence in S2 → verify in S3/S4) for the multimodal case specifically, and confirms NEI must be a first-class output, not a fallback. The retrieve-then-verify split mirrors your S2→S3 boundary.

### Adaptive Multimodal Fact-Checking with Visual Evidence Necessity (2026)
**URL:** https://arxiv.org/pdf/2604.04692

**Core technique:** Determines *when* visual evidence is actually necessary/sufficient to decide a claim, adaptively choosing whether to commit to a verdict or abstain based on evidence necessity.

**Maps to your pipeline:** Directly targets two of your weak spots at once - it's a principled **abstention/calibration** policy for the NEI class, and the "is the visual evidence sufficient for THIS claim?" gate is essentially your `evidence_standard_met` / `valid_image` columns. Use it to decide NEI vs a committed verdict, which should lift both contradicted-precision and NEI accuracy.

---

## Bottom line for implementation (priority order)

1. **Add S3 attribute-level adjudication** (IdealGPT + VISTAR `verify()` schema): independently check object/part/issue_type/severity, with `issue_type` mismatch → `contradicted`. This is the direct fix for contradicted-recall 2/5.
2. **Neutral-first questioning + falsification prompt** (HallusionBench + counterfactual methods): ask "what damage is visible?" and "what would prove this claim false?" *before* anchoring on the claim. Zero training, immediate recall gain.
3. **Adopt SNLI-VE's exact contradiction definition** ("enough evidence the claim is false," and a *different visible issue counts as contradiction*) in the S4 decision tree and the S3 prompt wording.
4. **FEVER evidence-gate for abstention**: only emit supported/contradicted with a concrete `supporting_image_id`; else `not_enough_information`. Cleans up NEI accuracy and fills `supporting_image_ids`.
5. **Evidence-necessity gate** (2604.04692) for principled NEI vs commit calibration, mapped to `evidence_standard_met` / `valid_image`.

**Sources:**
- https://arxiv.org/abs/1901.06706 (SNLI-VE / Visual Entailment task)
- https://github.com/necla-ml/SNLI-VE
- https://arxiv.org/pdf/2507.17467 (VLM visual-entailment pitfalls - your bug confirmed)
- https://arxiv.org/pdf/2305.14985 (IdealGPT decomposition)
- https://arxiv.org/pdf/2505.08084 (VISTAR Subtask-of-Thought `verify()` schema)
- https://arxiv.org/pdf/2409.19339 (Visual Question Decomposition) · https://arxiv.org/pdf/2308.09970 (Inner Monologue for VE)
- https://arxiv.org/pdf/2310.14566 (HallusionBench)
- https://www.researchgate.net/publication/401147486 (CounterfactualLVLM) · https://arxiv.org/html/2511.19923v1 (CounterVQA) · https://arxiv.org/html/2506.21546v1 (HalluSegBench)
- https://github.com/NishilBalar/Awesome-LVLM-Hallucination
- https://arxiv.org/pdf/2511.12140 (backward visual grounding / atomic-claim verification)
- https://arxiv.org/abs/1803.05355 · https://aclanthology.org/N18-1074/ · https://github.com/awslabs/fever (FEVER)
- https://arxiv.org/pdf/2205.12487 (MOCHEG multimodal SUP/REF/NEI)
- https://arxiv.org/pdf/2604.04692 (adaptive visual-evidence necessity / abstention)

---

## LLM-as-Judge / Verification / Abstention (Agent C)

I now have all the evidence I need across all four research areas, including the critical caveats. Here is my research report.

---

# Agent C Research: Multimodal LLM-as-Judge, Verification & Confidence-Based Abstention

Findings for the supported/contradicted/NEI decision, mapped to your pipeline. All techniques are **inference-time / prompting only** - no training, no GPUs. Every one is implementable as 1-3 extra Claude Code headless calls per row.

---

## TL;DR - what to actually build (ranked by ROI for your weak spots)

| Recipe | Targets | Extra calls/row | Expected lift | Confidence |
|---|---|---|---|---|
| **1. Verify-then-decide (CoVe) with per-attribute checks, draft-blind** | contradicted-recall (2/5) | +1 | High - directly attacks "single-look bias" | Strong evidence |
| **2. Self-consistency vote on the S4 verdict (k=5, then majority)** | issue_type, severity, contradicted | +4 | +2-18% on reasoning-style decisions | Very strong evidence |
| **3. Agreement-as-abstention -> route to NEI** | NEI quality, risk_flags over-flagging | 0 extra (reuse #2 samples) | +2pt selective accuracy at fixed coverage | Strong evidence |
| **4. Cascaded judge: cheap Sonnet read -> Opus only on disagreement** | overall reliability at low cost | +0 to +1 (only ~20-40% of rows) | matches strong-judge accuracy at fraction of cost | Strong evidence (ICLR'25 oral) |
| **5. Cross-model (Sonnet vs Opus) disagreement as epistemic-uncertainty gate** | confident-but-wrong NEI cases | +1 | +2pt selective accuracy where self-consistency collapses | Strong evidence |

**Do NOT** add a naive "are you sure?" critic loop or a self-refine pass without an external check - the evidence below shows it *hurts* on exactly your kind of task.

---

## Part 1 - Which self-correction / debate techniques actually help (and which don't)

This matters because the intuitive move - "add a critic that second-guesses S4" - is the one the literature says backfires.

### 1.1 Self-correction without an external signal degrades accuracy (the key negative result)

**Large Language Models Cannot Self-Correct Reasoning Yet** (Huang et al., ICLR 2024)
URL: https://arxiv.org/abs/2310.01798 · OpenReview: https://openreview.net/pdf?id=IkmD3fKBPQ
- Core: When prior work showed self-correction gains, the gains came *only* because an **oracle label** was used to decide when to stop correcting. Remove the oracle and "intrinsic" self-correction **reliably degrades** reasoning accuracy - the model talks itself out of correct answers.
- Maps to pipeline: A CriticAgent that re-reads its own S4 verdict and asks "are you sure?" with no new evidence will *lower* your contradicted-recall and severity accuracy. Any critic you add must consume a *new external signal* (a fresh image read, a per-attribute check, a second model) - never pure introspection.

**The FlipFlop Experiment: Challenging LLMs Leads to Performance Drops** (Laban et al., 2023)
URL: https://arxiv.org/abs/2311.08596 (arXiv 2311.08596)
- Core: Challenging an LLM's answer ("are you sure?") triggers **sycophantic flipping** - models abandon correct answers and accuracy drops substantially even when the original answer was right.
- Maps to pipeline: Confirms the above. Do not implement an adversarial "are you sure the dent is real?" turn. If you want challenge, use **independent re-derivation** (resample / second model), not interrogation of the existing answer.

**Surveying self-correction strategies** (Pan et al., 2023)
URL: https://arxiv.org/abs/2308.03188
- Core: Comprehensive taxonomy. Self-correction works **when and only when there is reliable external feedback** (tools, retrieval, a verifier). Pure self-critique from fast models produces "uninformative critiques."

### 1.2 The forms of self-correction that DO help: external-feedback verification

**CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing** (Gou et al., ICLR 2024)
URL: https://arxiv.org/abs/2305.11738 (overview: https://beancount.io/bean-labs/research-logs/2026/04/26/critic-llm-self-correct-tool-interactive-critiquing)
- Core: Generate -> verify against an *external* signal (search, interpreter, classifier) -> correct. The verification, not the introspection, is what fixes errors.
- Maps to pipeline: Your "external signal" for image claims is **a fresh, narrowly-scoped vision call** that re-looks at the image to answer one verification question (see CoVe below). That is the legitimate critic.

### 1.3 Chain-of-Verification (CoVe) - the single most relevant technique for contradicted-recall

**Chain-of-Verification Reduces Hallucination in LLMs** (Dhuliawala et al., Findings of ACL 2024)
URL: https://arxiv.org/abs/2309.11495 · ACL: https://aclanthology.org/2024.findings-acl.212/
- Core (4 steps): (i) draft answer; (ii) **plan verification questions**; (iii) **answer them independently - draft-blind, so the model cannot copy its own hallucination**; (iv) produce a final, verified answer. No training. The decisive design detail is step (iii): if the verifier sees the draft, it re-confirms the same error.
- Maps to pipeline - **this is your contradicted-recall fix**. Your failure mode ("dent claimed, only a scratch shown, part matches") is a classic confirmation hallucination: S2/S4 latches onto the claimed issue. Add a CoVe stage **S3-verify** between S2 and S4:
  1. From S1 claim, generate targeted yes/no verification questions: *"Is there a concave deformation/dent visible on the {part}? Y/N + where."* / *"Is the visible damage consistent with a {claimed_issue}, or only a {alternative}?"*
  2. Issue these as a **separate vision call that does NOT see the claim text or the S2 issue_guess** - it only sees the image and the neutral question. This breaks the single-look bias.
  3. S4 decision tree then compares claimed_issue vs verified_issue. Mismatch on issue while part matches -> **contradicted**, exactly the case you miss today.

### 1.4 Multi-agent debate - helps factuality but expensive; use the cheap variant

**Improving Factuality and Reasoning through Multiagent Debate** (Du, Tenenbaum, Mordatch et al., 2023)
URL: https://arxiv.org/abs/2305.14325 · Project: https://composable-models.github.io/llm_debate/
- Core: Multiple model instances critique each other's reasoning over rounds; disagreements get "debated out." ~7% mean accuracy lift; gains **plateau after ~3-4 rounds and ~5 agents**. Cost scales with agents x rounds.
- Maps to pipeline: Full debate is over budget for a hackathon CSV run. The *useful, cheap residue* of this result is: **disagreement between two independent reads is a strong error signal.** Capture that with self-consistency (#2) or cross-model disagreement (#5) instead of a full multi-round debate.

---

## Part 2 - Self-consistency: the highest-evidence, easiest win

**Self-Consistency Improves Chain of Thought Reasoning** (Wang et al., ICLR 2023)
URL: https://arxiv.org/abs/2203.11171
- Core: Sample k diverse reasoning paths at temperature, take the **majority-vote answer**. Pure inference-time. Reported gains: GSM8K +17.9%, SVAMP +11.0%, AQuA +12.2%.
- Maps to pipeline: Apply to the **S4 verdict** (and to S2's `issue_guess`/`severity_guess`). Run S2->S4 k=5 times at temperature ~0.7, majority-vote each output field (claim_status, issue_type, severity). This directly attacks your severity (0.70) and issue_type (0.75) accuracy, because those are exactly the "well-posed, single-correct-answer" fields self-consistency is built for.
- Cost: +4 calls/row (k=5). If budget-tight, vote only on the *uncertain* rows (rows where the first sample's verdict is contradicted/NEI, or where #5 flags disagreement).

**Estimating the Self-Consistency of LLMs** / self-consistency as a confidence proxy
URL: https://arxiv.org/pdf/2509.19489
- Core: The *spread* of the k samples is itself a usable confidence estimate - tight agreement = confident, scattered = uncertain. You get a calibration signal for free from the same k samples. This feeds Part 3.

---

## Part 3 - Confidence calibration & selective prediction (your NEI decision)

The central, well-replicated finding: **don't ask the model for its confidence number.** Use *agreement across samples/models* and *evidence coverage* instead.

### 3.1 Why verbalized confidence is the wrong abstention signal

**Are LLM Decisions Faithful to Verbal Confidence?** (2026)
URL: https://arxiv.org/abs/2601.07767 (arXiv 2601.07767)
- Core: "Decoupling of confidence and policy" - even when a model's verbalized confidence is *somewhat* calibrated, it fails to convert that into a good abstain/answer decision. Self-reported "I'm 90% sure" does not reliably gate behavior.

**Wired for Overconfidence** (2026)
URL: https://arxiv.org/abs/2604.01457
- Core: Verbalized confidence is mechanistically **inflated/overconfident**. Confirms you cannot threshold on a stated percentage to decide NEI.

**Know Your Limits: A Survey of Abstention in LLMs** (TACL)
URL: https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00754/131566 · arXiv: https://arxiv.org/abs/2407.18418
- Core: Survey of abstention. Best signals for *when to abstain* are **consistency across samples** and **input/evidence-coverage gates**, not introspective confidence.
- Maps to pipeline: Your `not_enough_information` verdict should be **triggered by signals, not by the model declaring uncertainty**: (a) the k self-consistency samples disagree on claim_status; (b) cross-model disagreement (#5); (c) an explicit **evidence-coverage gate** - if S2/S3 returns `has_visible_damage = unclear` OR `quality_issues` (blur/crop) OR the claimed part is not visible in any image, force NEI. This is deterministic and reproducible, which fits your constraints.

### 3.2 Agreement-based abstention with a guarantee

**Mitigating LLM Hallucinations via Conformal Abstention** (Yadkori et al., 2024)
URL: https://arxiv.org/abs/2405.01563
- Core: Use the LLM to score **similarity among its own k sampled responses**; apply **conformal prediction** to set the abstain threshold so the error rate is provably bounded at a chosen level. Less conservative than logprob-based abstention. No training.
- Maps to pipeline: With your ~20 labeled examples as a tiny **calibration set**, you can conformally pick the agreement threshold at which you flip to NEI such that the verdict-error rate on *non-abstained* rows is bounded (e.g., <=10%). This is the principled way to set the NEI cutoff with only 20 labels - you can't fine-tune, but 20 points is enough for a conformal quantile.

**Selective "Selective Prediction": Reducing Unnecessary Abstention in Vision-Language Reasoning** (2024)
URL: https://arxiv.org/abs/2402.15610
- Core: VLMs over-abstain; a lightweight selective-prediction calibration recovers coverage without losing accuracy.
- Maps to pipeline: Guards against the opposite failure - over-using NEI - so you tune the gate to abstain only when signals genuinely conflict.

---

## Part 4 - Ensembling cheap + strong models, disagreement-as-abstention

### 4.1 The cascade you described (Sonnet read -> Opus adjudication) - validated and principled

**Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement** (Jung, Brahman, Choi - ICLR 2025, Oral)
URL: https://arxiv.org/abs/2407.18370 · ICLR: https://iclr.cc/virtual/2025/oral/31838
- Core: **Cascaded Selective Evaluation** - a *cheap* judge handles each item; the system estimates the judge's confidence (via "Simulated Annotators," a sampling-based calibration, not verbalized confidence) and **escalates to a stronger model only when the cheap judge isn't confident enough**. Provides a *provable* bound on agreement with the human/gold standard at a user-chosen level, while using mostly the cheap model.
- Maps to pipeline - **this is exactly your "Sonnet read + Opus adjudication" idea, done right.** Recipe:
  1. Run S2->S4 with **Sonnet** (cheap) k times; estimate confidence as sample agreement (Simulated-Annotators style), not a self-reported number.
  2. If agreement >= calibrated threshold -> **trust Sonnet's verdict** (~60-80% of rows, near-zero extra cost).
  3. Else **escalate that row to Opus** for adjudication. Only the hard ~20-40% of rows pay Opus cost.
  - Result shape: strong-judge accuracy at a fraction of strong-judge cost, with a coverage/agreement guarantee. Perfect fit for the hackathon time budget.

### 4.2 Cross-model disagreement as an epistemic-uncertainty / abstention signal

**Complementing Self-Consistency with Cross-Model Disagreement for Uncertainty Quantification** (2026)
URL: https://arxiv.org/abs/2604.17112 (arXiv 2604.17112) · OpenReview: https://openreview.net/forum?id=lOoRJo8xWy
- Core: Self-consistency (one model resampled) **collapses on "confident-but-wrong"** cases - the model repeats the same wrong answer, so intra-model agreement looks high. **Cross-model semantic disagreement** catches exactly those: it is *higher on incorrect answers precisely when single-model uncertainty is low*. Total uncertainty = intra-model (aleatoric) + cross-model (epistemic). Concrete budget: 2 samples each from 5 auxiliary models = 10 samples total. Reported: HotpotQA 66.9% vs 64.9% selective accuracy at 90% coverage.
- Maps to pipeline: Your NEI failures are likely "confident-but-wrong" - one model reading an image confidently mislabels the issue. Recipe: get the verdict from **two different models** (Sonnet and Opus). **Agreement -> accept. Disagreement -> abstain to NEI (or escalate per #4.1).** Disagreement-as-abstention is the cheapest reliable NEI trigger you can add (+1 call/row).

### 4.3 Critical caveat: don't fake a panel with one model family

**Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels** (2026)
URL: https://arxiv.org/abs/2605.29800 (arXiv 2605.29800)
- Core: A 9-judge panel across 7 model families provides only **~2.2 effective independent votes** - judges make the *same* mistakes on the same items. Panel accuracy ran **8-22 points below** the independent-voting ideal, and **the single best judge matched or beat the whole panel.** Adding judges past ~5 gives negligible benefit. Diversity must be in *how models reason*, not just brand names.
- Maps to pipeline - two hard rules:
  1. **Don't** stack 5 Claude calls and call it an independent ensemble - correlated errors mean you're paying 5x for ~2x of real signal. Self-consistency (#2) is still worth it for *voting*, but for *abstention* you need genuine independence.
  2. For real independence, make the two reads **structurally different**: e.g., Sonnet-with-CoVe-questions vs Opus-single-shot, or two different *prompt decompositions* of the image. Disagreement between *genuinely different reasoning paths* is the signal worth abstaining on.

### 4.4 General multimodal judge bias (informs prompt hygiene)

**From Generation to Judgment: Opportunities and Challenges of LLM-as-a-Judge** (survey, 2024)
URL: https://arxiv.org/abs/2411.16594
**LLMs-as-Judges: A Comprehensive Survey** (2024)
URL: https://arxiv.org/abs/2412.05579 (HTML: https://arxiv.org/html/2412.05579v2)
- Core: Judges (incl. multimodal) show **verbosity bias, position bias, self-preference bias**, and prefer "authoritative-looking" outputs. Single MLLM-as-judge scores are unstable.
- Maps to pipeline: In your S4 prompt, neutralize bias: present the claim and the image-facts **without leading the verdict**; randomize/abstract the order of "supported vs contradicted vs NEI"; force the model to **state the visual evidence before the verdict** (describe-before-decide, Part 5). Don't let a verbose claim sway a "supported."

---

## Part 5 - Describe-before-decide / perception-before-reasoning for VLMs (structure your S2/S3)

This directly hardens the per-image fact extraction that feeds your deterministic S4, and attacks issue_type and contradicted-recall at the source.

**Perception Before Reasoning** (2025)
URL: https://arxiv.org/abs/2509.13031
- Core: VLMs must *accurately perceive the image first*; bolting reasoning onto weak perception is the main error source. Separating perception from reasoning improves visual-reasoning accuracy.
- Maps to pipeline: You already do this (S2 facts -> S4 tree). Reinforce it: make S2 emit **objective, claim-blind** observations only (shapes, textures, deformation present/absent, locations) and forbid it from naming the issue relative to the claim. The *labeling* (scratch vs dent) should be a separate, explicit perceptual judgment with a definition ("dent = concave deformation of the surface; scratch = surface-level line, no deformation"), so S4 can catch a claimed-dent / observed-scratch mismatch.

**CoRGI: Verified Chain-of-Thought with Post-hoc Visual Grounding** (2025)
URL: https://arxiv.org/abs/2508.00378 (pdf)
- Core: Each reasoning step is **grounded back into visual evidence** by a verification module before it's trusted - step-wise visual verification reduces ungrounded claims.
- Maps to pipeline: Require S3-verify to return **where in the image** the damage is (a region/bbox or description). If it can't ground the claimed damage to a location, that's an evidence-coverage failure -> NEI. Grounding requirement also reduces over-flagging of `risk_flags`.

**CrossCheck-Bench: Diagnosing Compositional Failures in Multimodal Conflict Resolution** (2025) + multi-attribute contradiction findings
URL: https://arxiv.org/pdf/2511.21717
- Core: VLMs have a **"single-look bias"** and **fail badly at multi-attribute contradiction detection** - they affirm implausible attribute combinations with high confidence. This is precisely your contradicted-recall bug.
- Maps to pipeline: Decompose the verdict into **independent per-attribute checks** rather than one holistic judgment: separately verify (a) object matches, (b) **part** matches, (c) **issue type** matches, (d) **severity** matches. Your current tree already checks part; add an **independent issue-type check** that does not assume the claim. A contradiction on issue-with-part-matching is your missed case - make it a first-class branch.

### Atomic decomposition (the general principle behind CoVe + CrossCheck)

The recurring, training-free pattern across these: **decompose the global verdict into atomic, independently-verified claims** ("damage present?", "damage = dent?", "located on bumper?", "severity = major?"). Verify each in isolation, draft-blind, then let your deterministic S4 tree combine them. This isolates errors and is the single highest-leverage change for both contradicted-recall and risk_flags precision (a flag only fires if its specific atomic check passes).

---

## Concrete implementation plan (fits a few extra calls/row + ~20 labels)

1. **S2 hardening (0 extra calls):** make per-image facts claim-blind and add explicit dent-vs-scratch and severity definitions (Perception-Before-Reasoning, CoRGI).
2. **Add S3-verify (+1 call):** CoVe-style targeted yes/no verification questions per claimed attribute, issued draft-blind, with visual grounding required. -> contradicted-recall.
3. **Self-consistency on uncertain rows (+0 to +4 calls):** k=5 resample of S2->S4, majority-vote the fields. -> issue_type, severity. Only fire on rows S3/S5 flags as uncertain to save budget.
4. **Cross-model disagreement gate (+1 call):** Sonnet read vs Opus read; agree -> accept, disagree -> NEI or escalate. -> confident-but-wrong NEI.
5. **Cascade routing (Trust-or-Escalate):** Sonnet handles confident rows, Opus only adjudicates the disagreements from step 4. -> reliability at low cost.
6. **Conformal NEI threshold:** use the ~20 labels as a conformal calibration set to set the agreement cutoff for NEI with a bounded error guarantee. -> principled abstention with tiny data.
7. **Risk_flags precision:** make each flag a separate atomic check that must independently pass (atomic-decomposition); never flag manual-review/history from holistic vibes. -> micro-F1.

**Avoid:** any introspective "are you sure?" / self-refine pass on the existing verdict with no new evidence (Huang ICLR'24; FlipFlop) - it lowers accuracy. All correction must consume a *new* signal (fresh image read, second model, atomic check).

### Primary sources
- https://arxiv.org/abs/2203.11171 (Self-Consistency)
- https://arxiv.org/abs/2309.11495 (Chain-of-Verification)
- https://arxiv.org/abs/2310.01798 (LLMs Cannot Self-Correct Yet)
- https://arxiv.org/abs/2311.08596 (FlipFlop / sycophancy)
- https://arxiv.org/abs/2305.14325 (Multiagent Debate)
- https://arxiv.org/abs/2407.18370 (Trust or Escalate - cascaded selective eval, ICLR'25)
- https://arxiv.org/abs/2604.17112 (Cross-Model Disagreement UQ)
- https://arxiv.org/abs/2605.29800 (Nine Judges, Two Effective Votes)
- https://arxiv.org/abs/2405.01563 (Conformal Abstention)
- https://arxiv.org/abs/2601.07767 (Verbal Confidence not faithful) / https://arxiv.org/abs/2604.01457 (Overconfidence)
- https://arxiv.org/abs/2407.18418 (Know Your Limits - abstention survey)
- https://arxiv.org/abs/2402.15610 (Selective "Selective Prediction" for VLMs)
- https://arxiv.org/abs/2509.13031 (Perception Before Reasoning)
- https://arxiv.org/abs/2508.00378 (CoRGI - visual grounding verification)
- https://arxiv.org/pdf/2511.21717 (CrossCheck-Bench - single-look / multi-attribute contradiction)
- https://arxiv.org/abs/2411.16594 + https://arxiv.org/abs/2412.05579 (LLM-as-judge bias surveys)

---

## Image Authenticity + Multi-label Precision (Agent D)

I now have everything needed. Compiling the final report.

---

# Agent D Report: Image Authenticity Signals + Multi-Label Flag Precision

Grounded in your actual code at `code/images/authenticity.py` (EXIF + pHash priors only today) and `code/domain/decision_tree.py` (`_should_require_manual_review`, `_MANUAL_REVIEW_TRIGGERS`, `_is_usable_evidence`). Two themes: (A) training-free authenticity signals to add, (B) inference-time multi-label precision to cut over-emission of `manual_review_required` / `user_history_risk`.

---

## A. Image Authenticity / Forgery Signals (training-free, laptop-runnable)

### A1. Error Level Analysis (ELA) — classical splice/edit signal

- **Sherloq** (the reference open-source forensic toolset): https://github.com/GuidoBartoli/sherloq
- Tutorial repos with copy-pasteable ELA in pure Pillow: https://github.com/ShivamGupta92/ImageForgeryDetection and https://github.com/harshita3002/imageforgeryDetection
- Background: https://www.infosecinstitute.com/resources/digital-forensics/error-level-analysis-detect-image-manipulation/

**Technique:** Re-save the JPEG at a known quality (e.g. 90), subtract from the original, and amplify. Genuinely untouched regions degrade uniformly under recompression; spliced/edited regions show anomalously high residual energy. ~15 lines with Pillow + NumPy, deterministic, CPU-instant.

**Maps to your pipeline:** Add `ela_max_residual` / `ela_anomaly_ratio` to `exif_signals()` (rename it to a generic `authenticity_signals()`). Feed a HIGH residual into the `possible_manipulation` prior. **Critical caveat (this is your over-flagging risk):** ELA fires false positives on any re-saved/edited-but-honest photo, text overlays, and high-frequency texture (the GuidoBartoli README itself warns it is "not meant as an automatic tool that decides if an image is forged"). So gate it conservatively: only contribute to the prior on a STRONG, localized anomaly, never on a borderline global value. ELA on a PNG is meaningless (no JPEG history) - skip it when format != JPEG.

### A2. JPEG Ghost / Double-Compression — strongest "was this re-saved/spliced" signal

- Block-level double-JPEG detection (method + reference): https://arxiv.org/pdf/2003.09393
- "Dual JPEG Compatibility" (2024, explainable, reliable): https://arxiv.org/pdf/2408.17106
- Sherloq implements ghost maps + quantization-table extraction + "multiple compression detection."

**Technique:** A region recompressed at a different quality than the rest produces a "ghost" - a local minimum in re-compression error at the prior quality factor. Detects content pasted from a differently-compressed source. The quantization-table read alone is a cheap tell: phone-camera tables differ from Photoshop/screenshot-export tables.

**Maps to your pipeline:** Read the JPEG quantization table (via Pillow `img.quantization`) in `authenticity.py`. A non-standard/editor-style table strengthens the existing `has_editor_software_tag` and `is_screenshot_like` priors that already feed `non_original_image`. **Caveat:** every social-media / chat-app re-upload double-compresses honest images, so on its own it is a weak prior, not a verdict - keep your invariant that these never flip `claim_status`.

### A3. Copy-Move (clone) detection — duplicated regions within one image

- Pure-Python copy-move: https://github.com/rahmatnazali/image-copy-move-detection
- Forensic-ToolKit (SIFT-based copy-move + EXIF): https://github.com/mightyshibbu/Forensic-ToolKit

**Technique:** SIFT/ORB keypoints + block matching find regions cloned within the same image (e.g. a dent pasted twice, or a scratch duplicated to look worse). Training-free, runs on CPU in seconds.

**Maps to your pipeline:** Optional `possible_manipulation` contributor. **Caveat:** false-positives on legitimately repetitive textures (grilles, keyboards, tiled packaging). For a 24h hackathon this is lower ROI than A1/A2 - list it but deprioritize.

### A4. TruFor / Noiseprint++ — SOTA learned localization, but a deliberate NON-recommendation

- Project: https://grip-unina.github.io/TruFor/ · Paper: https://openaccess.thecvf.com/content/CVPR2023/papers/Guillaro_TruFor_Leveraging_All-Round_Clues_for_Trustworthy_Image_Forgery_Detection_and_CVPR_2023_paper.pdf
- Noiseprint: https://arxiv.org/pdf/1808.08396

**Technique:** Transformer fusing RGB with a learned camera-noise fingerprint (Noiseprint++); outputs a forgery localization map, an integrity score, AND a reliability/confidence map that suppresses false alarms. Pretrained test weights released.

**Maps to your pipeline:** This is the right model conceptually, but it needs PyTorch weights + ideally a GPU and is NOT trivially callable through Claude Code headless with no API. **Recommendation: do NOT integrate for the hackathon.** Cite it as the principled upgrade path and instead approximate its philosophy (multiple weak forensic clues + an explicit confidence gate) with the classical signals above.

### A5. EXIF / metadata anomalies — you already have this; tighten it

Your `exif_signals()` already reads Make/Model/Software and screenshot resolutions. Cheap additions:
- **Thumbnail-vs-full mismatch:** an embedded EXIF thumbnail that doesn't match the full image is a classic edit tell (Forensic-ToolKit, Sherloq both do this).
- **EXIF timestamp inconsistency** (DateTimeOriginal vs DateTime vs file mtime).
- **C2PA / Content Credentials:** https://opensource.contentauthenticity.org/docs/c2pa-python/ — official `c2pa-python` (PyPI, Py3.10+) verifies a cryptographically signed provenance manifest. If present and valid it's a STRONG authenticity *positive*; absence proves nothing (most images lack it). Spec: https://spec.c2pa.org. **Use only as a positive signal**, never absence-as-guilt.

**Caveat that directly drives your over-flagging:** absent EXIF is extremely common for honest images (every screenshot, every messaging-app re-upload, every WhatsApp/iMessage strip). Your `has_camera_exif == False` should be a very weak prior. **Do not let missing-EXIF alone push `non_original_image`** or you will over-emit and drag `valid_image` false, which (via `_should_require_manual_review` returning True when `valid_image` is False) auto-fires `manual_review_required`. This is a likely root cause of your low flag precision.

### A6. Perceptual-hash dedup / recycled-image — you have it; calibrate the threshold

- ImageHash lib (you use it): https://github.com/JohannesBuchner/imagehash
- Empirical Hamming distributions for threshold selection: https://www.sciencedirect.com/science/article/pii/S2666281723000100
- PHASER eval framework: https://www.sciencedirect.com/science/article/pii/S2666281723001993
- pHash vs deep-embedding dedup comparison: https://www.mdpi.com/2079-9292/15/7/1493

**Technique:** Your `find_recycled()` uses pHash at `RECYCLED_HAMMING_THRESHOLD = 6`. Literature: 5 bits is the historical "same image" line for 64-bit pHash; **6 is on the loose side and inflates false positives** on visually similar but distinct photos (two different dented bumpers). The Hamming-distribution papers show inter-class (different image) pHash distances cluster well above 10, so tightening to **≤4-5** cuts false `non_original_image` flags with negligible recall loss on true re-submissions.

**Maps to your pipeline:** Lower `RECYCLED_HAMMING_THRESHOLD` to 4 or 5, and consider requiring agreement across pHash AND dHash before flagging (cuts single-algorithm false matches; the comparative studies note dHash ~= pHash so the agreement is cheap and decorrelates errors).

### A7. Screenshot / stock / watermark / overlay-text detection

- Watermark detection survey/approach framing: https://restb.ai/solutions/watermark-detection/ and overlay-text dataset https://arxiv.org/pdf/2211.11350
- Screenshot exact-resolution match: you already do this in `_SCREENSHOT_RESOLUTIONS`.

**Technique:** You already infer screenshots from exact panel resolutions. For watermark/stock: a watermark is a semi-transparent repeated overlay - detectable via high-frequency periodic texture, but unreliable as a standalone. The more robust, hackathon-appropriate move is to **let your Claude vision call do this**: it already returns `embedded_text` and an `authenticity` field. A vision model reliably reports "stock-photo watermark," "Getty/Shutterstock banner," or "screenshot UI chrome" far better than a classical heuristic. **Recommendation: keep watermark/stock detection in the perception prompt, not in `authenticity.py`.**

### A8. AI-generated-image detection — explicit DO-NOT-USE for 2026

- Sanity-check paper (ICLR 2025): https://proceedings.iclr.cc/paper_files/paper/2025/file/b0303773962ea1b5394c3a83cc7dd066-Paper-Conference.pdf
- Comprehensive review: https://arxiv.org/pdf/2502.15176 · ScienceDirect 2026 review: https://www.sciencedirect.com/science/article/pii/S1574013726000171
- Open-source detector benchmark (2026): https://arxiv.org/pdf/2602.07814

**State of the art / verdict:** Standard generators (Midjourney/DALL-E/SD) are detected ~80-95% in-distribution, but **no detector reliably exceeds ~80% across datasets**, they **generalize poorly to unseen generators**, and they **throw false positives on heavily-edited real photographs** (exactly your damage-claim case: cropped, filtered, re-saved real photos). Pipelines that add real camera characteristics drop detection below 50%.

**Recommendation: do NOT add a standalone AI-gen detector.** False-positive rate on legitimately-edited honest claim photos is unacceptable and would crater your already-struggling flag precision. If you want any AI-gen signal at all, route it through the Claude vision `authenticity` field as a soft observation, never as a hard `possible_manipulation` trigger.

---

## B. Multi-Label `risk_flags` Precision (no training, inference-time)

Your F1 is 0.56 with over-emission of `manual_review_required` and `user_history_risk`. The fixes are threshold/rule discipline, not a classifier.

### B1. Per-label thresholds, not one global rule — F1-optimal thresholding

- F1-optimal thresholding in the multi-label setting: https://www.researchgate.net/publication/260126882_F1-Optimal_Thresholding_in_the_Multi-Label_Setting
- Threshold-selection study (Lin et al., NTU): https://www.csie.ntu.edu.tw/~cjlin/papers/threshold.pdf
- Thresholding for infrequent labels: https://www.csie.ntu.edu.tw/~cjlin/papers/thresholding/smooth_acm.pdf

**Technique:** Each label gets its own decision threshold tuned to maximize F1 on a validation set; a single 0.5 cutoff is provably suboptimal under micro-F1. **Key result for you:** *infrequent labels should require HIGHER confidence to fire.* Micro-F1's global optimum is cheaply findable. With only ~20 labeled examples you can't grid-search per label, but you CAN apply the qualitative rule: rare, costly flags (manual_review, history, manipulation) must clear a higher bar than common quality flags.

**Maps to your pipeline:** Today `_should_require_manual_review` fires if ANY trigger is in the set OR `valid_image` is False - a fixed OR, the loosest possible rule. Replace with a tiered policy: each trigger flag carries an implicit confidence, and `manual_review_required` fires only on a HIGH-confidence trigger.

### B2. Calibrate when to abstain / emit `manual_review_required` — content-moderation framing

- "Reliable Decision from Multiple Subtasks through Threshold Optimization: Content Moderation in the Wild": https://arxiv.org/pdf/2208.07522
- Human-machine interaction framework (2026): https://arxiv.org/html/2601.05974
- Adaptive multi-label thresholding (2025): https://arxiv.org/html/2505.03118v1

**Technique:** In production moderation, set **human precision as the lower bound** and maximize recall *subject to* that precision floor - route to a human (your `manual_review_required`) only when confidence clears a precision-preserving threshold; below it, treat as non-violative rather than escalating. T > 0.5 for precision-critical labels, T < 0.5 only when recall is imperative.

**Maps to your pipeline directly:** `manual_review_required` is your "escalate to human" label and it's over-firing. Apply the moderation rule:
- **Drop `valid_image == False` as an automatic manual-review trigger** in `_should_require_manual_review`. A blurry/cropped honest photo makes `valid_image` False via `_is_usable_evidence`, then auto-escalates - but your own `domain/AGENTS.md` invariant says a *benign coverage gap alone must NOT trigger review*. The `not valid_image: return True` branch contradicts that invariant and is a prime false-positive source. Make manual-review fire ONLY on the genuine trust triggers (`claim_mismatch`, `wrong_object`, `non_original_image`, `possible_manipulation`, `text_instruction_present`, `user_history_risk`), not on pure unusability.

### B3. Label-dependency / mutual-exclusion rules — free precision from logical constraints

- Adaptive thresholding via global-local signal fusion (encodes label co-dependence): https://arxiv.org/html/2505.03118v1
- Unified view of multi-label measures (which labels co-occur, how micro-F1 rewards): https://arxiv.org/pdf/1609.00288

**Technique:** Enforce known label-dependency / mutual-exclusion constraints at inference. If labels are logically exclusive or implied, prune the contradictory/redundant one - directly raising precision with zero training.

**Maps to your pipeline (concrete rules to add to `decision_tree.py`):**
- **Mutual exclusion:** `damage_not_visible` and a specific issue-type flag shouldn't co-occur; `wrong_object` implies you should NOT also emit part-level quality flags (`wrong_angle`, `blurry_image`) since the object is already wrong - prune them.
- **Dominance:** when `wrong_object` fires you already add `claim_mismatch`; don't also stack quality flags - the verdict is decided. Collapse to the decisive flag set.
- **`user_history_risk` suppression:** today it's added purely from `history.is_risky` independent of the image verdict. Apply the rule *history never flips status AND should rarely stand alone*: only surface `user_history_risk` when the row is ALSO `contradicted` or already has another trust flag. On a cleanly `supported` row with good imagery, a risky-history flag is almost always a false positive against gold - suppress it. This single rule likely recovers a large chunk of your lost precision, since history over-flagging is named as a top weak spot.

### B4. How to optimize micro-F1 at inference

- Surrogate/global threshold optimization (low compute): https://arxiv.org/pdf/2103.00833
- Calibration insight: if outputs are well-calibrated probabilities, the optimal F1 threshold ≈ half the optimal F1 value: https://www.researchgate.net/publication/256822740_Threshold_optimisation_for_multi-label_classifiers

**Technique:** Micro-F1 pools all label decisions, so it's dominated by your high-frequency flags - meaning **a few over-emitted common flags (manual_review/history) on many rows hurt micro-F1 more than missing a rare flag.** The cheap inference-time win is to bias toward NOT emitting the frequently-wrong flags. With 20 examples, pick thresholds/rules by leave-one-out on your sample set (you already have `evaluation/cross_validation.py`) and choose the rule config that maximizes micro-F1 on held-out folds - a legitimate, training-free tuning loop.

---

## Concrete change list

**`code/images/authenticity.py`:**
1. Add ELA residual signal (JPEG-only) -> contributes to `possible_manipulation` ONLY on strong localized anomaly.
2. Read JPEG quantization table -> reinforce `non_original_image`/screenshot priors (never standalone).
3. Lower `RECYCLED_HAMMING_THRESHOLD` 6 -> 4-5; optionally require pHash AND dHash agreement.
4. Add EXIF thumbnail-mismatch + timestamp-inconsistency checks.
5. Optional: `c2pa-python` as a positive-only authenticity signal.
6. Demote missing-EXIF to a very weak prior; never let it alone set `non_original_image`.
7. Do NOT add an AI-gen detector or TruFor; keep watermark/stock/AI-gen judgments in the Claude vision `authenticity` field.

**`code/domain/decision_tree.py` (`_should_require_manual_review` + flag assembly):**
8. Remove the `if not valid_image: return True` auto-escalation (contradicts your own benign-coverage-gap invariant; top false-positive source).
9. Gate `user_history_risk` so it surfaces only alongside `contradicted` or another trust flag - never on a clean `supported` row.
10. Add mutual-exclusion pruning: when `wrong_object` fires, drop part-level quality flags; don't stack redundant quality flags once the verdict is decided.
11. Tune the resulting rule config by leave-one-out on the 20 samples via existing `cross_validation.py`, selecting for micro-F1.

The highest-ROI, lowest-risk wins given your constraints: **#8 and #9** (rule tightening, pure determinism, no new deps) and **#3** (one-line threshold change). ELA (#1) and quantization-table (#2) are the best new authenticity signals; everything learned/AI-gen is explicitly deferred as unreliable for 2026.

---
