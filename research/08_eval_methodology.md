# Evaluation Methodology for n=20 (research conclusion)

> Workflow wf_8707d152-729, 2026-06-19. How to calibrate without overfitting 20 labels.

## CONCLUSION (Agent 3)

I have everything I need from the two reports. Let me synthesize the decisive recommendation.

# Agent 3 — Synthesis & Decision: The Evaluation Methodology for This Pipeline

## The verdict in one line

**Reject the 70/30 split.** Use **LOOCV (all 20 rows) as the working calibration signal + a frozen 4-row stress holdout opened exactly once at the end + Wilson 95% CIs on every reported number**, and govern overfitting through an **iteration budget and rule-provenance discipline**, not through a fancier resampler. Both upstream reports converged on this independently; the only thing left to do is make it concrete and resolve the two small tensions between them.

The user's instinct is *the right fear applied with the wrong tool*. The fear (overfitting / non-generalization) is exactly what the rubric grades. But at n=20 a single 14/6 split is the **worst** realistic option: a 6-row test set has a Wilson 95% CI of roughly ±25-30 points, moves in 16.7-point quanta, cannot distinguish a 90% pipeline from a coin flip, and routinely strands the 2 NEI rows entirely on one side. It throws away 30% of an already-starved dataset *and* fails to validate. Worse, it does not even address the real overfitting channel here: there are no weights to overfit. The overfitting risk is **you, the human, hand-tuning rules against the visible labels** (researcher degrees of freedom). A split does not stop that — you would just tune against 14 rows instead of 20.

---

## 1. THE RECOMMENDED PROTOCOL

**Three layers. Each does a distinct job.**

### Layer A — LOOCV is the headline working signal (uses all 20, including both NEI)

Run leave-one-out: 20 iterations, each trains on 19 / tests on 1, every row tested exactly once.

Why LOOCV specifically (and not stratified k-fold as the *primary*):

- **It is the only scheme where every rare row is used in training in 19 of 20 iterations and tested exactly once.** No NEI / `evidence_standard_met=false` / `severity=high` example is ever stranded entirely in a test fold or entirely in train. With only 2 NEI rows, stratified 5-fold *cannot even place an NEI example in all 5 folds* — at most 2 folds get one. LOOCV sidesteps that.
- **Deterministic — no random-split luck.** For a rule/prompt pipeline you want the same 20 verdicts every run so a threshold change is attributable to the change, not to a reshuffle.
- **Cheap here.** 20 API runs is trivial; the usual "LOOCV is 20× expensive" objection (built for retraining big models) does not bite.
- **It produces 20 individual errors to cluster** — the single highest-value artifact at this n (see §4 of the calibration loop).

### Layer B — Stratified 5-fold as the *secondary reported* number + the train-vs-held-out gap

Report stratified 5-fold (preserving the 13/5/2 ratio) **alongside** LOOCV. Its job is **not** to be the headline — it is to (a) give a second estimate that should roughly agree with LOOCV (disagreement = instability flag) and (b) expose the **in-fold vs held-out-fold accuracy gap**, which is your main quantitative overfit signal for a deterministic pipeline. If in-fold is 95% and held-out is 70%, you have tuned to specifics.

### Layer C — A frozen 4-row stress holdout ("lockbox"), opened exactly once

Carve out **4 rows immediately, before any tuning**, stratified to contain **1 NEI + 1 contradicted + 1 `evidence_standard_met=false` + 1 supported**. Never look at it during iteration. Open it **once, at the very end**, to report the train-vs-lockbox gap as a final honesty check.

**This is the one place I resolve a tension between the reports.** Agent 1 said "use all 20, no holdout, LOOCV does it all." Agent 2 said "keep a 3-4 row lockbox." **Agent 2 wins, with a caveat.** Here is the reasoning: pure LOOCV iterated against repeatedly *still* leaks signal through researcher degrees of freedom — after enough tweaks your LOOCV number is itself a multiple-comparisons artifact and there is nothing left that is "clean." A tiny frozen holdout is the only thing that can give a genuinely untouched gap number at the end. **The caveat (Agent 1's valid point): 4 rows is statistically near-worthless as an accuracy measurement — it is a directional smoke test, not a metric.** So we keep it, we open it once, and we report it as "the gap was small/large" with an explicit "n=4, not a metric" disclaimer — never as a headline percentage. That gives the rubric the affirmative "I held something back and it generalized" story without pretending 4 rows is precise.

### Why this beats a naive 70/30 split at n=20

| | Naive 70/30 (14/6) | This protocol |
|---|---|---|
| Data used to calibrate | 14 rows | 20 rows (LOOCV) |
| NEI coverage | Often **0 NEI** in test or train | Both NEI always in training 19/20 iters |
| Headline CI | ±25-30 pp on 6 rows | ±15 pp on 20 (still wide, but honest) |
| Granularity | 16.7 pp/row | 5 pp/row |
| Clean final check | none (the 6 are "spent") | 4-row lockbox, opened once |
| Stops the real overfit (RDoF) | No | Yes (via §2 budget) |

### How rare classes are preserved

- **NEI (n=2) and the false-evidence/high-severity singletons are treated as named case studies, not statistics.** Report "did it get both NEI? why did it miss?" qualitatively. NEI accuracy is at best a 2-row, 50-pp-granularity measurement no matter what method you pick — say so, do not dress it as a percentage.
- **Do NOT use SMOTE / synthetic oversampling.** That would invent claim cases that do not exist and corrupt the error analysis. Accept that NEI is measured on 2 real rows.

---

## 2. THE CALIBRATION LOOP (overfitting-resistant)

The governing insight: **the overfitting channel here is researcher degrees of freedom, not model capacity.** Therefore the control is *discipline on iterations*, not a better resampler.

**Step 0 — Pre-register rules BEFORE looking at labeled outcomes.**
Write the decision tree from `dataset/evidence_requirements.csv` + the gold philosophy first. Commit it. *Then* run it against the 20. This is the LLM analog of pre-registration: rules chosen without peeking at outcomes.

**Step 1 — Carve the 4-row lockbox immediately (Layer C). Set it aside. Do not touch.**

**Step 2 — Run LOOCV on all 20. Read the 20 individual results, not just the mean.**

**Step 3 — Diagnose failures by ROOT CAUSE, not by row.**
For each miss ask: *"what principle did my rule miss?"* Fix the **principle**, not the example. A change justified by an error *pattern* (a whole class of car/dent claims, the NEI logic) generalizes; a change that rescues exactly one row (Δ = 1/20) with no principled reason is memorization — reject it.

**Step 4 — Re-run the FULL LOOCV harness after every change** (golden set as regression guard) so you catch "fixing row A broke row B" drift.

**Step 5 — Budget the iterations. Hard cap: ~8-12 substantive changes total.**
This is the most important anti-overfit lever. Each look-tweak-rescore cycle leaks signal; past ~10 hand-tweaks you will find a rule set that scores well on these exact 20 by luck. Log every change + its data-justification. When you hit the cap, **stop** — the dev signal is no longer meaningful. Fewer optimization steps is a documented overfit-reducer (early stopping).

**Step 6 — When two candidate prompts/thresholds have overlapping Wilson CIs (they will, at n=20), pick on PRINCIPLE, not the score delta.** A 0.85 vs 0.80 gap at n=20 is noise. Choose the one with better minority-class *reasoning*, and write down that you did. (Relative ranking on the dev set is more trustworthy than the absolute level — but only when CIs separate, which they rarely will here.)

**Step 7 — Keeping the holdout clean:** the lockbox is opened **once, after Step 5's cap is hit and the final config is frozen.** It informs *zero* knobs. If the lockbox is worse than the dev set, **report the gap honestly** — a disclosed small gap is more credible than a hidden one.

**When is the dev signal dead?** After the iteration cap (~10), or when changes start only moving single rows with no class-level rationale, or when LOOCV and stratified-5-fold start disagreeing (instability). Whichever comes first.

---

## 3. WHAT TO IMPLEMENT IN `code/evaluation/`

Build into the existing harness (`code/evaluation/{main.py,metrics.py,compare.py}`):

1. **`loocv_runner.py`** — runs the 20-fold leave-one-out, returns per-row predictions + the 20 individual error records (with `claim_object`, `issue_type`, true vs predicted class) for clustering. This is the primary entry point.
2. **`stratified_kfold.py`** — repeated stratified 5-fold (e.g. 5 folds × 5 shuffled repeats) preserving the 13/5/2 ratio; emits mean held-out accuracy **and the in-fold vs held-out gap**.
3. **`wilson.py`** — Wilson (or Clopper-Pearson) 95% CI for a proportion. **Every metric the harness prints must carry its Wilson CI.** Wald/normal CIs are invalid below a few hundred points.
4. **`lockbox.json`** (or `.csv`) — the 4 frozen row IDs, stratified (1 NEI / 1 contradicted / 1 false-evidence / 1 supported), committed once. A guard in the runner asserts these IDs are **excluded from all LOOCV/k-fold tuning runs** and only scored by an explicit `--open-lockbox` flag used at the very end.
5. **Per-field metrics** — claim_status, evidence_standard_met, severity, valid_image, supporting_image_ids each scored separately (multi-output), each with its own Wilson CI.
6. **≥2-strategy comparison in `compare.py`** — runs two prompts/thresholds on the *identical* LOOCV harness and prints both with CIs, **flagging overlap** ("CIs overlap; selected B on principle, not the delta"). The rubric requires a strategy comparison.
7. **A `rule_provenance` table/file** — each deterministic rule → the principle/source in `evidence_requirements.csv` it derives from. This is the affirmative proof you did not hardcode test answers.

### What `evaluation_report.md` must contain

1. **Methodology & why-not-split** — state n=20 is too small for a split; cite the single-error 16.7-pp swing and the ±25-pp 6-row CI. Pre-empt "why didn't you just split?"
2. **Headline table** — every metric as `0.85, 95% CI [0.64, 0.95]`, never a bare percentage.
3. **Per-fold variance** — min/max/std across folds; proves you checked stability.
4. **Train-vs-lockbox gap** — the one-shot number, with the "n=4, directional not metric" disclaimer.
5. **Small-n caveat box** (verbatim-style): *"With 20 labeled rows and 3 minority classes (2 NEI, 5 contradicted), no point estimate is precise to better than ±15-25 points. These numbers are a regression guard against rule breakage, not a forecast of test accuracy. We optimized for principled coverage of claim types, not for maximizing this score."*
6. **Rule-provenance table** — rule → `evidence_requirements.csv` principle. Explicitly NOT "row 7 was wrong so I added this."
7. **Strategy comparison** — 2 strategies on identical LOOCV, CIs, honest overlap flag.
8. **NEI / rare-class case studies** — qualitative, not percentages.

---

## 4. HONEST CAVEATS + THE AI-JUDGE ANSWER

**Caveats (state them, do not hide them):**
- No method recovers a precise accuracy number from 20 labels; even all-20 LOOCV has ±15 pp. Published LLM-judge calibration floors are ~50 traces for a balanced binary criterion, 200+ for rare classes. We have 20, with classes at 2-5 examples. The numbers are a **regression guard, not a forecast.**
- NEI is a 2-row measurement; the lockbox is a 4-row directional check. Neither is a metric.
- LOOCV carries known high variance and mild distributional bias on imbalanced data — which is exactly why we wrap it in Wilson CIs and cross-check with stratified 5-fold rather than reporting it bare.

**The 3-sentence answer to "how do you know it generalizes?":**

> "I don't claim a precise accuracy number — at n=20 with rare classes at 2-5 examples, any single figure has a ±15-25 point confidence band, so I report Wilson intervals, not bare percentages. What I'm confident in is **provenance**: every deterministic rule traces to `evidence_requirements.csv` and the published evidence standard, not to any specific labeled row — I can show you that mapping table — and I pre-registered the rules before scoring, capped my tuning iterations, fixed failures by correcting the underlying principle rather than patching individual rows, and held back a stratified lockbox I opened exactly once. So my claim isn't 'X% accuracy' — it's **principled coverage of every claim type and failure mode the 44 will contain, with the honest uncertainty stated**, which is the only defensible claim at this sample size."

---

## 5. DECISION-TREE CALIBRATION — DO / DON'T

**DO**
- Derive every threshold/rule from `evidence_requirements.csv` / the gold philosophy *first*, then test against the 20.
- Prefer the **fewest, most general** rules. Every special-case rule is an overfit smell.
- Fix failures by correcting the **principle**, justified by a class-level error pattern across the 20.
- Ablate each rule (toggle off, measure LOOCV delta): keep rules that help a *class* of cases; delete rules that only rescue one row.
- Re-run the full LOOCV harness after every change to catch "fixed A, broke B."
- Report every threshold's effect with a Wilson CI and pick on principle when CIs overlap.
- Maintain the rule → provenance mapping table as you go.

**DON'T**
- Don't add a row-specific patch ("row 7 is contradicted, so add a rule that catches row 7"). That is hardcoding test-shaped answers — the exact thing the rubric forbids.
- Don't do a 70/30 split, and don't chase the dev-set score the way Kaggle losers chase the public leaderboard (the 20 labels are your "public LB"; robust CV + principled rules survive on the hidden 44).
- Don't exceed ~10-12 substantive tuning iterations; past that the dev signal is a multiple-comparisons artifact.
- Don't SMOTE / synthetically oversample the rare classes — it invents fake claims and corrupts error analysis.
- Don't use nested CV — with a handful of hand-set knobs and a human in the loop, the selection bias it removes is tiny and the variance it adds at n=20 (outer folds of ~4 rows) is enormous; it is "overzealous" here.
- Don't report a bare percentage anywhere, and don't touch the lockbox until the final, frozen run.

### Key sources
LOOCV / k-fold / bias-variance: [Raschka arXiv:1811.12808](https://arxiv.org/pdf/1811.12808), [Raschka k-fold FAQ](https://sebastianraschka.com/faq/docs/number-of-kfolds.html). Small-n CI / no-CLT: [arXiv:2503.01747](https://arxiv.org/pdf/2503.01747), [Wilson CI](https://www.statisticshowto.com/wilson-ci/), [CI-width table arXiv:2404.13020](https://arxiv.org/pdf/2404.13020). Stratification under imbalance: [scikit-learn CV](https://scikit-learn.org/stable/modules/cross_validation.html), [PMC9967638](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9967638/). Nested-CV overkill: [Wainer & Cawley arXiv:1809.09446](https://arxiv.org/abs/1809.09446). LOOCV distributional bias: [arXiv:2406.01652](https://arxiv.org/pdf/2406.01652). Researcher degrees of freedom / prompt overfitting: [RDoF Wikipedia](https://en.wikipedia.org/wiki/Researcher_degrees_of_freedom), [arXiv:2211.02219](https://arxiv.org/pdf/2211.02219), [arXiv:2309.03409](https://arxiv.org/pdf/2309.03409), [When "Better" Prompts Hurt arXiv:2601.22025](https://arxiv.org/html/2601.22025v1). LLM-judge calibration sizing / reporting: [dev.to 50-vs-200](https://dev.to/maya_andersson_dev/calibration-set-size-for-llm-as-judge-when-50-traces-is-enough-and-when-200-is-mandatory-d1d), [arXiv:2511.21140](https://arxiv.org/pdf/2511.21140). Tiny-labeled + large-unlabeled practice: [Kaggle anti-overfit](https://www.kaggle.com/discussions/getting-started/175133).

**Relevant local files:** `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/sample_claims.csv` (20 labeled; 13/5/2), `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/claims.csv` (44 unlabeled), `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/evidence_requirements.csv` (rule-provenance source), `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/code/evaluation/{main.py,metrics.py,compare.py}` (harness to extend with `loocv_runner.py`, `stratified_kfold.py`, `wilson.py`, `lockbox.json`).

---

## ML methodology (Agent 1)

I now have all the quantitative grounding and authoritative citations needed. Here is the deliverable.

---

# Agent 1 — ML Evaluation Methodology for Tiny Labeled Sets (n=20)

## Bottom line up front

For a **deterministic LLM/VLM pipeline with a handful of human-set rules/thresholds**, evaluated on **n=20 labeled rows**, a single fixed 70/30 hold-out split is **statistically meaningless** for accepting or rejecting a calibration change. The accuracy estimate on a 6-row test set carries a **±25–30 percentage-point 95% confidence interval** and can only move in 16.7 pp jumps. The correct protocol is **Stratified k-fold (k=5) for honest reporting + Leave-One-Out CV (LOOCV) as the working signal during tuning, with all 20 rows used, and a hard cap on the number of calibration changes you make** so you don't burn through the dataset via researcher degrees of freedom. Nested CV is **not** warranted at this scale and for this few "hyperparameters."

I verified the data: `dataset/sample_claims.csv` (absolute path `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/sample_claims.csv`) has exactly 20 rows with `claim_status` = **13 supported / 5 contradicted / 2 not_enough_information**, plus even rarer signals (`evidence_standard_met=false`: 2; `valid_image=false`: 2; `severity=high`: 1). The 44 test rows are in `dataset/claims.csv`. The rare-class problem is real and is the binding constraint on methodology.

---

## 1. Is a single fixed train/test split statistically meaningful at n=20?

**No.** A 70/30 split = 14 train / 6 test. The accuracy you read off 6 points is a binomial proportion with `k/6` resolution, so the estimate moves in **16.7-percentage-point quanta** and nothing finer is observable. Below a few hundred datapoints the CLT/normal (Wald) approximation has wrong coverage, so you must use **Wilson or Clopper–Pearson exact** intervals ([Bowyer et al., "Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints," arXiv:2503.01747](https://arxiv.org/pdf/2503.01747); [Wilson interval coverage notes](https://www.statisticshowto.com/wilson-ci/)).

I computed the actual Wilson 95% CIs for every possible result on a 6-row test set:

| Test result (k/6) | Observed accuracy | Wilson 95% CI | CI width |
|---|---|---|---|
| 6/6 | 100% | [61%, 100%] | 39 pp |
| 5/6 | 83% | [44%, 97%] | **53 pp** |
| 4/6 | 67% | [30%, 90%] | 60 pp |
| 3/6 | 50% | [19%, 81%] | **62 pp** |
| 2/6 | 33% | [10%, 70%] | 60 pp |
| 1/6 | 17% | [3%, 56%] | 53 pp |
| 0/6 | 0% | [0%, 39%] | 39 pp |

**Read this carefully:** a pipeline that scores **5/6 (83%)** on the held-out test set has a true accuracy that is statistically indistinguishable from anything between **44% and 97%**. You cannot tell a genuinely good pipeline (90%) from a coin-flip-ish one (50%) with 6 test points. A single split gives **dangerously high variance whenever n_test is small (here, catastrophically so at 6) and whenever the true accuracy is near 50%** (widest interval), which is exactly the regime where you most need to discriminate between two candidate prompts.

The same accuracy at larger n shrinks the interval, showing how starved n=6 is:

| n (test) | ~83% acc | Wilson 95% CI | width |
|---|---|---|---|
| **6** | 5/6 | [44%, 97%] | **53 pp** |
| 14 | 12/14 | [60%, 96%] | 36 pp |
| 20 | 17/20 | [64%, 95%] | 31 pp |
| 40 | 33/40 | [68%, 91%] | 23 pp |
| 100 | 83/100 | [74%, 89%] | 15 pp |

Two practical corollaries at n=20: even using **all 20 rows** as one evaluation set, the granularity is 1/20 = 5 pp and the 95% CI on an 83% result is still ±15 pp wide. So **no method recovers tight estimates from 20 labels** — the goal of methodology here is to *not waste data and not fool yourself*, not to produce a publishable accuracy number.

---

## 2. Realistic options at n=20, compared

| Method | What it does at n=20 | Pros | Cons / variance at this size | Fit for prompt/threshold tuning |
|---|---|---|---|---|
| **Single hold-out (70/30)** | 14 train, 6 test, one estimate | Trivial; mimics the "real" submission split | Estimate has ±25–30 pp CI; 16.7 pp granularity; result depends entirely on *which* 6 rows landed in test; rare classes (2 NEI) often absent from one side | **Poor.** Too noisy to rank two prompts; wastes 30% of already-tiny data |
| **k-fold CV (k=5)** | 5 folds of 4; train on 16, test on 4, rotate | Every row is tested exactly once; uses all 20; averages out split luck; k=5/10 is the empirically recommended bias-variance sweet spot ([Raschka, arXiv:1811.12808](https://arxiv.org/pdf/1811.12808); [Raschka fold-count FAQ](https://sebastianraschka.com/faq/docs/number-of-kfolds.html)) | Folds of 4 are tiny; a single rare-class row dominates its fold; fold-to-fold accuracy is jumpy | **Good** as the headline metric, **if stratified** |
| **Stratified k-fold (k=5)** | k=5 but each fold preserves the 13/5/2 ratio | Guarantees rare classes are represented across folds; standard fix for imbalance ([scikit-learn StratifiedKFold](https://apxml.com/courses/getting-started-with-scikit-learn/chapter-5-model-selection-evaluation/stratified-kfold-classification); [Szeghalmy & Fazekas, PMC9967638](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9967638/)) | With only **2 NEI rows**, even stratification can't put one in all 5 folds — at most 2 folds get an NEI example | **Best honest report.** Lower variance than plain k-fold for imbalanced data |
| **LOOCV** | 20 iterations, train on 19, test on 1 | Uses maximum data per iteration (lowest bias); deterministic — no random-split luck; every row scored individually → ideal for **error-pattern inspection** | High variance of the estimate; the 20 per-row results are correlated; computationally 20× (cheap for an LLM pipeline, but 20 API runs); can be pessimistically/distributionally biased on imbalanced data ([distributional bias in LOOCV, arXiv:2406.01652](https://arxiv.org/pdf/2406.01652)) | **Best working signal during iteration** — see §5. Cannot stratify (test fold = 1 row), but uses every rare row |
| **Bootstrap .632** | Resample 20 with replacement, ~63% in-bag, test on out-of-bag | Smooths the estimate; gives an empirical sampling distribution; recommended as a CI method when CLT fails ([arXiv:2503.01747](https://arxiv.org/pdf/2503.01747)) | Out-of-bag folds vary in size; .632 weighting assumptions get shaky with rare classes and a deterministic (non-learning) pipeline; resampling 2 NEI rows is unstable | **Secondary** — useful as a *stability/CI check* (see §4), not as the primary tuning metric |
| **Nested CV** | Inner loop tunes, outer loop scores | The textbook unbiased way to evaluate *tuned* models ([Raschka, arXiv:1811.12808](https://arxiv.org/pdf/1811.12808); [nested CV intro](https://machinelearningmastery.com/nested-cross-validation-for-machine-learning-with-python/)) | At n=20 the outer folds are absurdly small (≈4 rows each, inner ≈16); estimate is pure noise; massive overkill | **Not warranted** — see §3. Wainer & Cawley show nested CV is "overzealous for most practical applications" when there are **few hyperparameters** ([arXiv:1809.09446](https://arxiv.org/abs/1809.09446)) |

**Bias-variance framing** (the governing tradeoff): more folds → lower bias, higher variance and cost; fewer folds → lower variance, higher bias. LOOCV is the maximum-fold extreme: lowest bias, highest variance. k=5/10 is the recommended compromise ([Raschka FAQ](https://sebastianraschka.com/faq/docs/number-of-kfolds.html); [PSU STAT 897D](https://online.stat.psu.edu/stat857/node/161/)).

---

## 3. The decisive point: you are tuning a few human-set rules, not fitting thousands of weights

This changes the right protocol fundamentally, and most ML-eval intuition (which assumes gradient training of many parameters) **over-applies** here.

- **Degrees of freedom are tiny.** Your "model" is a handful of thresholds and prompt phrasings — maybe a dozen tunable knobs, not millions. The classic overfitting mechanism (a high-capacity learner memorizing 14 training rows) **is largely absent**. There are no weights to overfit; there is no train/test leakage through SGD.
- **Therefore the *primary* overfitting risk is "researcher degrees of freedom" / adaptive overfitting to the dev set**, not model capacity. Every time you look at the 20 labels, tweak a threshold, and re-score, you implicitly fit *yourself* to those 20 rows. This is a **multiple-comparisons problem**: after enough hand-tweaks, you will find a rule set that scores well on these exact 20 by luck, and it won't generalize to the 44 ([Researcher degrees of freedom, Wikipedia](https://en.wikipedia.org/wiki/Researcher_degrees_of_freedom); [minP adjustment for RDoF, PMC11253496](https://pmc.ncbi.nlm.nih.gov/articles/PMC11253496/); [prompt-tuning overfitting, arXiv:2211.02219](https://arxiv.org/pdf/2211.02219)).
- **Consequence for protocol:** the right control is **not** a fancier resampling scheme — it's **discipline on the number of calibration iterations** and treating the dev set as a scarce, depleting resource. Budget your tweaks (e.g. ≤10–15 substantive changes total), prefer changes justified by a *reason in the data* (an error pattern) over changes that merely nudge the score, and write down each change and its rationale.
- **Nested CV is the wrong tool.** Nested CV exists to de-bias *automated* hyperparameter search over many configurations. With few knobs and a human in the loop, Wainer & Cawley find flat CV gives "for all practical purposes" the same model selection — nested CV is "overzealous" and just destroys your already-tiny folds ([arXiv:1809.09446](https://arxiv.org/abs/1809.09446)). The bias nested CV removes is small *precisely because* you have few hyperparameters; the variance it adds at n=20 is enormous.
- **Note on prompt-overfitting:** when candidate prompts overfit "to a similar extent," higher dev accuracy still tracks higher true accuracy ([arXiv:2309.03409, OPRO](https://arxiv.org/pdf/2309.03409)). So relative ranking on the dev set is more trustworthy than the absolute number — lean on *comparisons*, distrust the *level*.

---

## 4. Detecting overfitting to the calibration set when you cannot see the test labels

You have 44 unlabeled test rows and can never score them. Use these blind diagnostics:

1. **Train-vs-dev gap via CV.** Compare in-fold (training) accuracy to held-out-fold accuracy across the stratified CV. A large gap (e.g. 95% in-fold vs 70% held-out) signals you've tuned to specifics. With a deterministic rule pipeline this gap is your main quantitative overfit signal.
2. **Stability under resampling.** Re-run stratified k-fold with different random seeds / different fold assignments, or bootstrap the 20 rows. If your accuracy and — more importantly — your *decisions* swing wildly when 2–3 rows move folds, the calibration is fragile and over-fit to the exact 20 ([arXiv:2503.01747](https://arxiv.org/pdf/2503.01747) on bootstrap for unstable small-n estimates).
3. **Ablation of each hand-set rule/threshold.** Turn each rule off and measure the LOOCV delta. A rule that only helps one specific row (Δ = 1/20) and has no principled justification is memorization; a rule that helps a *class* of cases generalizes. Prefer rules with broad, explainable effect.
4. **Confidence calibration.** Have the VLM/decision-tree emit a confidence per prediction and check whether confidence tracks correctness (reliability diagram / ECE). A pipeline that is confidently wrong on held-out folds is overfit and will mislead on the 44.
5. **Error-pattern inspection (the highest-value blind check).** LOOCV gives you all 20 individual errors. Cluster them: are mistakes concentrated in one `claim_object` (car/laptop/package), one `issue_type`, or the rare NEI class? Systematic, explainable errors are *fixable and generalizable*; scattered one-off "fixes" that each rescue a single row are RDoF overfitting. This is the single most informative thing you can do at n=20.

---

## 5. Stratification and rare classes (13 supported / 5 contradicted / 2 NEI)

The binding constraint is **not the 13/5 split — it's the 2 NEI rows** (and the even rarer signals: 2× `evidence_standard_met=false`, 1× `severity=high`).

- **Plain random hold-out fails the rare classes.** With 2 NEI in 20, a random 14/6 split frequently puts **0 NEI in test** (or 0 in train), so you either can't evaluate NEI handling at all or can't calibrate it. This alone disqualifies the single-split approach.
- **Stratified k-fold is the right *reporting* tool but caps out.** Stratification preserves the 13/5/2 ratio per fold ([scikit-learn StratifiedKFold](https://apxml.com/courses/getting-started-with-scikit-learn/chapter-5-model-selection-evaluation/stratified-kfold-classification); [GeeksforGeeks](https://www.geeksforgeeks.org/machine-learning/stratified-k-fold-cross-validation/)). But with 2 NEI rows you literally cannot place an NEI example in all 5 folds — at most 2 folds will contain one. So **NEI accuracy is, at best, a 2-row measurement (granularity 50 pp)** no matter what you do. Report NEI performance qualitatively (did it get both? why did it miss?), not as a percentage.
- **Is LOOCV the only way to use all the rare data?** Effectively, yes — **LOOCV is the only scheme where every rare row is used for training in 19 of 20 iterations and tested exactly once**, so no rare example is ever stranded entirely in a test fold or entirely in train. That's its key advantage here and why it's the right *working* signal during iteration. Its cost is that it can't be stratified (a 1-row test fold has no class balance) and can carry distributional bias on imbalanced data ([arXiv:2406.01652](https://arxiv.org/pdf/2406.01652)). When even stratification can't form reliable folds, the literature's fallback is to combine it with over/under-sampling ([PMC9967638](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9967638/)) — but **do not synthetically resample (SMOTE) a rule-tuning eval set**; it would invent claim cases that don't exist and corrupt your error analysis. Just accept that NEI is measured on 2 real rows.
- **Practical recommendation:** Use **LOOCV as the per-row working signal** (so all 20, including the 2 NEI, drive calibration), and **report Stratified 5-fold** as the honest aggregate with explicit per-class breakdown. Treat NEI and the false-evidence/high-severity cases as **named case studies**, not statistics.

---

## Ranked recommendation table (method → when to use at n=20)

| Rank | Method | Use it for | Why, at n=20 with 13/5/2 | Citation |
|---|---|---|---|---|
| **1** | **LOOCV + per-row error inspection** | Primary *working* signal while you iterate on prompts/thresholds | Uses every row (incl. both NEI) in training 19/20 times; gives 20 individual errors to cluster; deterministic, no split luck; cheap for an LLM pipeline | [Raschka 1811.12808](https://arxiv.org/pdf/1811.12808), [distributional-bias caveat 2406.01652](https://arxiv.org/pdf/2406.01652) |
| **2** | **Stratified 5-fold CV** | Headline accuracy you report + train-vs-held-out gap | Preserves 13/5/2 ratio; k=5 is the bias-variance sweet spot; better than plain k-fold under imbalance | [Raschka FAQ](https://sebastianraschka.com/faq/docs/number-of-kfolds.html), [PMC9967638](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9967638/), [StratifiedKFold](https://apxml.com/courses/getting-started-with-scikit-learn/chapter-5-model-selection-evaluation/stratified-kfold-classification) |
| **3** | **Wilson / Clopper–Pearson CI on the pooled CV result** | Reporting honest uncertainty (always show the interval, never a bare %) | CLT/Wald is invalid below a few hundred points; exact intervals have correct coverage | [arXiv:2503.01747](https://arxiv.org/pdf/2503.01747), [Wilson CI](https://www.statisticshowto.com/wilson-ci/) |
| **4** | **Bootstrap .632 / seed-shuffled CV** | Stability check — does accuracy *and decisions* hold under resampling? | Flags fragile calibration overfit to the exact 20 rows | [arXiv:2503.01747](https://arxiv.org/pdf/2503.01747) |
| **5** | **Single 70/30 hold-out** | Avoid for acceptance decisions; at most a final sanity smoke-test | 6-row test → ±25–30 pp CI, 16.7 pp granularity, rare classes often absent; wastes 30% of data | [arXiv:2503.01747](https://arxiv.org/pdf/2503.01747) |
| **✗** | **Nested CV** | **Do not use** | Few hand-set knobs + human-in-the-loop → selection bias is tiny and nested CV is "overzealous"; outer folds of ~4 rows are pure noise | [Wainer & Cawley 1809.09446](https://arxiv.org/abs/1809.09446) |

### Verdict on the user's hypothesis
The instinct ("split like ML, validate on held-out") is the *right concern* (avoid overfitting) but the *wrong mechanism* at this scale. A single 14/6 split is the **worst** of the realistic options: it throws away 30% of 20 labels, leaves a 6-row test that can't distinguish 50% from 90%, and routinely strands the 2 NEI rows. Replace it with **LOOCV-driven iteration + stratified-5-fold reporting + Wilson CIs**, and — because the real overfitting channel here is *researcher degrees of freedom*, not model capacity — **govern the number of calibration tweaks and justify each by a generalizable error pattern**, which is what the rubric's "rewards generalization, forbids file-specific answers" is actually testing.

### Sources
- [Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints — arXiv:2503.01747](https://arxiv.org/pdf/2503.01747)
- [Raschka, Model Evaluation/Selection/Algorithm Selection — arXiv:1811.12808](https://arxiv.org/pdf/1811.12808)
- [Raschka, choosing number of k-folds (FAQ)](https://sebastianraschka.com/faq/docs/number-of-kfolds.html)
- [Wainer & Cawley, Nested CV is overzealous for most practical applications — arXiv:1809.09446](https://arxiv.org/abs/1809.09446)
- [Distributional bias compromises leave-one-out CV — arXiv:2406.01652](https://arxiv.org/pdf/2406.01652)
- [Szeghalmy & Fazekas, Stratified vs distribution-balanced stratified CV in imbalanced learning — PMC9967638](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9967638/)
- [scikit-learn StratifiedKFold guide](https://apxml.com/courses/getting-started-with-scikit-learn/chapter-5-model-selection-evaluation/stratified-kfold-classification)
- [Stratified K-Fold — GeeksforGeeks](https://www.geeksforgeeks.org/machine-learning/stratified-k-fold-cross-validation/)
- [Wilson Confidence Interval — Statistics How To](https://www.statisticshowto.com/wilson-ci/)
- [Cross-validation — PSU STAT 897D](https://online.stat.psu.edu/stat857/node/161/)
- [Researcher degrees of freedom — Wikipedia](https://en.wikipedia.org/wiki/Researcher_degrees_of_freedom)
- [Addressing researcher degrees of freedom via minP adjustment — PMC11253496](https://pmc.ncbi.nlm.nih.gov/articles/PMC11253496/)
- [Understanding and Mitigating Overfitting in Prompt Tuning — arXiv:2211.02219](https://arxiv.org/pdf/2211.02219)
- [Large Language Models as Optimizers (OPRO), overfitting-to-similar-extent point — arXiv:2309.03409](https://arxiv.org/pdf/2309.03409)
- [Nested Cross-Validation intro — MachineLearningMastery](https://machinelearningmastery.com/nested-cross-validation-for-machine-learning-with-python/)

**Data verified locally:** `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/sample_claims.csv` = 20 rows, `claim_status` 13 supported / 5 contradicted / 2 NEI; rare signals `evidence_standard_met=false`×2, `valid_image=false`×2, `severity=high`×1. Test set: `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/claims.csv` (44 rows, unlabeled).

---

## Contest-practical (Agent 2)

I now have everything I need: the real data shape, the exact CI math, and authoritative sources spanning ML cross-validation theory, Kaggle small-data practice, LLM-as-judge calibration, and prompt-iteration overfitting. Here is the deliverable.

---

# Agent 2 Report — Contest-Practical Evaluation Design for n=20

## TL;DR (the recommendation, up front)

**Do NOT do an ML-style train/test split of the 20 labeled rows.** At n=20 with the label imbalance this dataset actually has (`claim_status` = 13 supported / 5 contradicted / 2 not-enough-info; `evidence_standard_met` = 18/2), a single held-out test split of ~6 rows is *statistical noise* — one wrong row swings accuracy by 17 points, and a 6-row test set's 95% confidence interval is roughly **±25 points wide** (Wilson). It cannot validate generalization; it can only mislead you and the judge.

**Use this instead — the defensible protocol:**
1. **All 20 rows stay as one evaluation set.** Headline metric = **Leave-One-Out CV (LOOCV)** because it maximizes data use and is near-unbiased.
2. **Report every metric with a Wilson 95% confidence interval**, not a bare point estimate. This is the single most important honesty signal.
3. **Decouple "calibration" from "the holdout."** Your decision-tree rules are *pre-registered from the gold philosophy / `evidence_requirements.csv`*, not fit row-by-row. The 20 labels are a **regression guard**, not a training set.
4. **Compare ≥2 strategies** (e.g., strict-vs-lenient prompt, or two threshold settings, or two models) on the same LOOCV harness, and report the gap *with overlapping CIs flagged honestly*.
5. **Touch a tiny "lockbox" holdout (3–4 rows) exactly once, at the very end**, as a sanity check on the train-vs-holdout gap — never as an iteration signal.

This reframes the problem correctly: **this is not model training, it is rule/prompt calibration on a tiny golden set.** The ML train/test mental model is the wrong tool, and saying so explicitly is what makes you look rigorous to the judge.

---

## 1. The honest + defensible protocol given only 20 labels

The user's hypothesis (split 20 → train/test, ML-style) is **unsound at this n**, and the literature is unambiguous about why. Three independent failure modes:

**(a) A single split at n=20 is noise, not validation.** With a typical 70/30 split you hold out ~6 rows. The math:
- One misclassified row = **16.7 percentage points** of accuracy swing.
- Wilson 95% CI for an observed 85.7% accuracy on **n=6 is [0.46, 0.98]** — a **52-point-wide** interval. On n=7 it is [0.49, 0.97]. You literally cannot distinguish "great" from "coin flip."
- scikit-learn and applied-ML guidance both note that with small data a single hold-out gives "strongly biased performance estimates," and the standard remedy is repeated/stratified CV, not one split ([scikit-learn CV docs](https://scikit-learn.org/stable/modules/cross_validation.html); [Müller, Applied ML data-splitting](https://amueller.github.io/aml/04-model-evaluation/1-data-splitting-strategies.html)).

**(b) Stratification breaks at this n + imbalance.** Your `claim_status` has only **2 "not_enough_information" rows and 5 "contradicted"**. A 30% test split can easily contain **zero** of a minority class, so the metric on that class is undefined and uninformative. Stratified k-fold exists precisely because "if some classes are very rare, a class may not be present at all in a particular fold" ([Stratified K-Fold, scikit-learn](https://scikit-learn.org/stable/modules/cross_validation.html); [MachineLearningMastery, CV for imbalanced classification](https://machinelearningmastery.com/cross-validation-for-imbalanced-classification/)). At n=20 you cannot stratify 3 classes into a clean train/test split.

**(c) The premise itself is mismatched.** There are **no weights to train**. "Overfitting" here does not come from a fit procedure; it comes from *you, the human, iterating prompts/thresholds against the visible labels.* The risk is the *experimenter* memorizing 20 rows, which a train/test split does **not** prevent — you'd just calibrate on 14 and still hand-tune toward them.

**What to do instead — LOOCV as the headline number.** Because each LOOCV fold trains on 19 and tests on 1, it is the least-biased estimator and "maximizes the use of available data" — the standard recommendation for small sets ([Keylabs, CV techniques](https://keylabs.ai/blog/cross-validation-techniques-for-classification-models/); [PMC, ML validation with limited sample size](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837442/)). Crucially, **LOOCV is honest at this n in a way a single split is not**, because the headline is the mean of 20 binary outcomes (SE ≈ 0.08 at p=0.85) rather than the mean of 6.

But LOOCV has a known weakness — **high variance** — so you do not report the bare LOOCV number alone ([arXiv 1011.0096, CV concentration](https://arxiv.org/pdf/1011.0096); [arXiv 2406.01652, distributional bias compromises LOOCV](https://arxiv.org/pdf/2406.01652)). You wrap it:
- **Wilson 95% CI** on the LOOCV accuracy (correct CI for proportions near 0/1 and small n — stable from n≈10, far better boundary coverage than the Wald/normal interval) ([Wilson interval, Tandfonline](https://www.tandfonline.com/doi/full/10.1080/09296174.2013.799918); [F1 CI comparison, arXiv 2309.14621]).
- **Per-field accuracy** (claim_status, evidence_standard_met, severity, valid_image, supporting_image_ids) each with its own Wilson CI, since the dataset is multi-output, not single-label.
- Optionally **repeated stratified k-fold (e.g., 5-fold × 5 repeats)** as a *secondary* number — repeating with shuffles is the recommended robustness check for small data ([analyticsvidhya, k-fold imbalanced](https://medium.com/analytics-vidhya/how-to-carry-out-k-fold-cross-validation-on-an-imbalanced-classification-problem-6d3d942a8016)).

**The answer to "how do you know it generalizes to the 44?"** is not "my held-out accuracy was X." It is: *"The rules were derived from the published evidence standard, not fit to these rows; the 20 labels only confirm the rules don't contradict ground truth; and I report the honest uncertainty band, which at n=20 is wide — so I make no precise accuracy promise, I demonstrate principled coverage of every claim type and failure mode the 44 will contain."*

---

## 2. What `evaluation_report.md` must contain to read as rigorous, not overfit

Structure it so a skeptical judge can audit each claim. Concretely, these sections:

**1. Methodology & split choice (with justification).**
State plainly: *"n=20 is too small for a train/test split; a 6-row holdout has a 95% CI of roughly ±25 points and cannot validate generalization. We therefore use LOOCV for the headline and repeated stratified 5-fold as a secondary check, every metric reported with a Wilson 95% CI."* Cite the single-error-swing number. This pre-empts the obvious "why didn't you just split?" question.

**2. The headline table — every metric with a CI.** Example shape (fill with real numbers):

| Field | LOOCV accuracy | Wilson 95% CI | n (labeled) |
|---|---|---|---|
| claim_status | 0.85 | [0.64, 0.95] | 20 |
| evidence_standard_met | 0.90 | [0.70, 0.97] | 20 |
| supporting_image_ids | … | … | 20 |

A bare "85%" reads as overfit bravado; "0.85, 95% CI [0.64, 0.95]" reads as someone who understands their own uncertainty. Reporting metrics without an uncertainty estimate at small n "is measuring noise" ([How to Correctly Report LLM-as-a-Judge, arXiv 2511.21140](https://arxiv.org/pdf/2511.21140); [dev.to calibration sizing](https://dev.to/maya_andersson_dev/calibration-set-size-for-llm-as-judge-when-50-traces-is-enough-and-when-200-is-mandatory-d1d)).

**3. Per-fold variance.** Show the spread across LOOCV/k-fold folds (min/max fold accuracy, std). This proves you looked at stability, not just the mean — and it honestly surfaces that minority-class folds are shaky.

**4. Train-vs-holdout gap (the one-shot lockbox).** Report the calibration-set accuracy vs the final lockbox (3–4 rows, opened once). If they're close, the gap is small → less overfit signal. If the lockbox is worse, *say so* — admitting a gap is more credible than hiding it. Prompt-iteration literature shows train accuracy often runs 5–20 points above held-out, so a small disclosed gap is normal and expected ([LLMs as Optimizers, arXiv 2309.03409](https://arxiv.org/pdf/2309.03409)).

**5. An explicit "small-n caveat" box.** One paragraph, verbatim-style: *"With 20 labeled rows and 3 minority classes (2 NEI, 5 contradicted), no point estimate here is precise to better than ±15–25 points. These numbers are a regression guard against rule breakage, not a forecast of test-set accuracy. We optimized for principled coverage of claim types and failure modes, not for maximizing this score."* This single box is the most disarming thing in the report — it tells the judge you already know the limitation they're about to raise.

**6. Rules-from-principles provenance (the gold philosophy).** A table mapping **each deterministic rule → the principle/source it came from**, e.g. `evidence_requirements.csv`, the published evidence standard, or domain logic — explicitly **not** "row 7 was wrong so I added this." Example: *"Rule: a 'car/dent' claim requires a same-object close-up → derived from evidence_requirements.csv's part-visibility requirement, applies to all dent claims, not tuned to any labeled row."* This is the crux of demonstrating generalization: the rubric forbids hardcoding test answers, and a principle-provenance table is the affirmative proof you didn't ([When 'Better' Prompts Hurt, arXiv 2601.22025](https://arxiv.org/html/2601.22025v1) — golden sets as *regression guards*, stratified by intent, not fit targets).

**7. Strategy comparison (≥2).** Required by the rubric. Show two prompts/thresholds/models on the *identical* LOOCV harness with CIs, and **honestly flag overlapping CIs**: *"Strategy B scored 0.85 vs A's 0.80, but CIs overlap heavily at n=20, so we selected B on principled grounds (better minority-class reasoning), not on the 5-point delta."* Selecting on principle when CIs overlap is exactly the Kaggle "trust your CV, not the noise" discipline.

---

## 3. Practical workflow — iterate without burning the holdout

The real overfitting risk is **multiple-comparisons against the labels**: every time you tweak a prompt and re-check the same rows, you leak a little signal and your number drifts upward without real generalization. Prompt-iteration research confirms "prompt drift" — refining to fix one case silently degrades others, and repeated checking inflates apparent quality ([When 'Better' Prompts Hurt, arXiv 2601.22025](https://arxiv.org/html/2601.22025v1); [zenvanriel, prompt testing frameworks](https://zenvanriel.com/ai-engineer-blog/prompt-testing-validation-frameworks/)).

The discipline that keeps the holdout valid:

1. **Pre-register the rule logic BEFORE looking at labeled outcomes.** Write the decision tree from `evidence_requirements.csv` + the gold philosophy first, commit it, *then* run it. This is the LLM analog of pre-registration — "hyperparameters chosen without peeking at the test set" ([scikit-learn / standard ML hygiene](https://scikit-learn.org/stable/modules/cross_validation.html)).

2. **Carve out a 3–4 row lockbox immediately and never look at it during iteration.** Stratify it to include 1 contradicted + ideally the rare NEI class. It is opened exactly once, at the end, for the §2.4 gap number. Held-out sets "never used for optimization decisions" is the explicit mitigation ([zenvanriel](https://zenvanriel.com/ai-engineer-blog/prompt-testing-validation-frameworks/)).

3. **Iterate ONLY on the ~16 dev rows, and diagnose failures by *root cause*, not by row.** When a row fails, ask "what *principle* did my rule miss?" and fix the principle — don't add a row-specific patch. Failure-driven augmentation should generalize the rule, not memorize the example ([arXiv 2601.22025](https://arxiv.org/html/2601.22025v1)).

4. **Version every prompt/threshold change and re-run the *full* LOOCV harness each time** (golden set as regression guard) so you catch the drift where fixing row A breaks row B. Cap your iteration budget (e.g., "≤8 prompt revisions") — early stopping / fewer optimization steps is a documented overfit-reducer ([LLMs as Optimizers, arXiv 2309.03409](https://arxiv.org/pdf/2309.03409)).

5. **Headline = LOOCV on the dev rows; final report adds the one-shot lockbox gap.** The lockbox number is a *check*, not a knob.

This way the holdout stays statistically valid (touched once) and your LOOCV number isn't a multiple-comparisons artifact.

---

## 4. How top practitioners handle tiny labeled + larger unlabeled (real practice)

This situation — calibrate on a few labels, predict a larger unlabeled set — is *exactly* the Kaggle "Don't Overfit!" archetype, and the established playbook is:

- **Trust local CV over the visible score; never chase the leaderboard.** The canonical Kaggle lesson: competitors who chase the *public* leaderboard "select models that overfit to the public test set, resulting in dramatic rank drops when private scores are revealed... final submissions should always include your most robust models based on cross-validation, not your highest public leaderboard scores" ([Kaggle: methods to prevent overfitting](https://www.kaggle.com/discussions/getting-started/175133); [Kaggle: combat over/underfitting](https://www.kaggle.com/discussions/getting-started/176441)). **Your 20 labels are your "public LB" — robust CV + principled rules are what survive on the hidden 44.**

- **Heavy regularization / maximum simplicity on small data.** Don't-Overfit-II winners used aggressive regularization and the *simplest* models that fit ([Towards Data Science, Don't Overfit II](https://towardsdatascience.com/dont-overfit-ii-how-to-avoid-overfitting-in-your-machine-learning-and-deep-learning-models-2ff903f4b36a/); [Analytics Vidhya, Don't Overfit II](https://medium.com/analytics-vidhya/kaggle-competition-dont-overfit-ii-74cf2d9deed5)). Your analog: **prefer the fewest, most general decision rules over a sprawling rule set with row-specific special cases.** Every special-case rule is an overfit smell.

- **Repeat CV with shuffles for a stable estimate** rather than betting on one split ([analyticsvidhya k-fold](https://medium.com/analytics-vidhya/how-to-carry-out-k-fold-cross-validation-on-an-imbalanced-classification-problem-6d3d942a8016)).

- **LLM-as-judge calibration practice — the exact numbers.** The state-of-practice for calibrating an LLM evaluator says: ~**50 stratified traces** pins a balanced binary criterion to a 95% bootstrap band of ±0.10–0.15; and for **rare classes you need 200+** ([dev.to: calibration set size](https://dev.to/maya_andersson_dev/calibration-set-size-for-llm-as-judge-when-50-traces-is-enough-and-when-200-is-mandatory-d1d)). **You have 20, with rare classes at 2–5 examples.** This is the strongest possible evidence that a single split is hopeless and that you must (a) use every row, (b) report Wilson CIs, (c) lean on principled rules to cover what the labels can't, and (d) report bias-corrected CIs that propagate calibration-set uncertainty ([How to Correctly Report LLM-as-a-Judge, arXiv 2511.21140](https://arxiv.org/pdf/2511.21140); [UW-Madison LLM-judge-reporting](https://github.com/UW-Madison-Lee-Lab/LLM-judge-reporting)).

- **CI width as a reality check (cite this verbatim to the judge):** with 25 / 50 / 100 / 250 labels, the 95% CI width around 0.75 accuracy is **0.36 / 0.25 / 0.17 / 0.11** respectively ([Stronger Random Baselines for ICL, arXiv 2404.13020](https://arxiv.org/pdf/2404.13020)). At your n=20 the band is wider than all of these — definitive proof that no precise accuracy claim is defensible, and that honesty about the band *is* the rigor.

---

## 5. What to tell the AI Judge — why the number is trustworthy despite n=20

Script (adapt wording, keep substance):

> "I want to be upfront that 20 labels is far below what's needed for a precise accuracy estimate — published LLM-judge calibration guidance puts the floor around 50 for a balanced binary criterion and 200+ when there are rare classes, and ours has classes with only 2–5 examples. So I deliberately did **not** do an ML train/test split: a 6-row holdout here has a 95% confidence interval roughly ±25 points wide and one wrong row swings it 17 points — that's noise, not validation, and reporting a single number off it would be dishonest.
>
> Instead I treated the 20 rows the way a Kaggle competitor treats the public leaderboard: a **regression guard, not a training target**. My headline is **leave-one-out CV** — the least-biased estimator at this n — and **every metric carries a Wilson 95% confidence interval** so the uncertainty is visible, not hidden. I compared two strategies on the identical harness; where their intervals overlapped I chose on **principle, not on the noise delta**.
>
> The reason I'm confident it generalizes to the 44 hidden rows isn't the accuracy number — it's the **provenance**. Every deterministic rule traces to the published evidence standard and `evidence_requirements.csv`, not to a specific labeled row; I can show you that mapping table. I pre-registered the rule logic before scoring, iterated only on a dev subset, fixed failures by correcting the *underlying principle* rather than patching individual rows, and opened a small lockbox holdout exactly once at the end to measure the train-vs-holdout gap, which I report honestly. So what I'm claiming isn't 'X% accuracy' — it's **principled coverage of every claim type and failure mode the 44 will contain, with the honest uncertainty stated.** That's the defensible claim at n=20; anything more precise would be overfitting to 20 rows."

This wins because it (1) raises the n=20 objection *before the judge does*, (2) names the correct estimator and CI, (3) cites the real calibration thresholds, (4) grounds generalization in rule-provenance not score, and (5) refuses to overclaim — which is itself the strongest signal of rigor.

---

## Relevant local files
- `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/sample_claims.csv` — 20 labeled rows; imbalance: claim_status 13/5/2, evidence_standard_met 18/2, severity skewed.
- `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/claims.csv` — 44 unlabeled rows (only user_id, image_paths, user_claim, claim_object).
- `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/dataset/evidence_requirements.csv` — **the gold-philosophy source**; cite it as the provenance for deterministic rules in the report.
- `/Users/tanishqsingh/Desktop/yash_desktop_files/projects/hackerrank-agent/code/evaluation/{main.py,metrics.py,compare.py}` — existing harness; add LOOCV + Wilson CI + repeated-k-fold + the ≥2-strategy comparison + lockbox here.

## Sources
- [scikit-learn — Cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html)
- [Müller — Applied ML, Data Splitting Strategies](https://amueller.github.io/aml/04-model-evaluation/1-data-splitting-strategies.html)
- [PMC — ML validation with limited sample size](https://pmc.ncbi.nlm.nih.gov/articles/PMC6837442/)
- [arXiv 1011.0096 — Concentration inequalities of the CV estimator](https://arxiv.org/pdf/1011.0096)
- [arXiv 2406.01652 — Distributional bias compromises LOOCV](https://arxiv.org/pdf/2406.01652)
- [Keylabs — Cross-validation techniques for classification](https://keylabs.ai/blog/cross-validation-techniques-for-classification-models/)
- [MachineLearningMastery — CV for imbalanced classification](https://machinelearningmastery.com/cross-validation-for-imbalanced-classification/)
- [Analytics Vidhya — k-fold CV on imbalanced data](https://medium.com/analytics-vidhya/how-to-carry-out-k-fold-cross-validation-on-an-imbalanced-classification-problem-6d3d942a8016)
- [Tandfonline — Binomial/Wilson confidence intervals](https://www.tandfonline.com/doi/full/10.1080/09296174.2013.799918)
- [arXiv 2309.14621 — Confidence intervals for the F1 score](https://arxiv.org/pdf/2309.14621)
- [arXiv 2404.13020 — Stronger Random Baselines for In-Context Learning (CI-width table)](https://arxiv.org/pdf/2404.13020)
- [dev.to — Calibration set size for LLM-as-judge (50 vs 200)](https://dev.to/maya_andersson_dev/calibration-set-size-for-llm-as-judge-when-50-traces-is-enough-and-when-200-is-mandatory-d1d)
- [arXiv 2511.21140 — How to Correctly Report LLM-as-a-Judge Evaluations](https://arxiv.org/pdf/2511.21140)
- [GitHub — UW-Madison LLM-judge-reporting (bias correction + CIs)](https://github.com/UW-Madison-Lee-Lab/LLM-judge-reporting)
- [arXiv 2601.22025 — When "Better" Prompts Hurt: Evaluation-Driven Iteration](https://arxiv.org/html/2601.22025v1)
- [zenvanriel — Prompt Testing and Validation Frameworks](https://zenvanriel.com/ai-engineer-blog/prompt-testing-validation-frameworks/)
- [arXiv 2309.03409 — Large Language Models as Optimizers (overfitting in prompt opt)](https://arxiv.org/pdf/2309.03409)
- [Kaggle — Methods to prevent overfitting](https://www.kaggle.com/discussions/getting-started/175133)
- [Kaggle — How to combat overfitting and underfitting](https://www.kaggle.com/discussions/getting-started/176441)
- [Towards Data Science — Don't Overfit II](https://towardsdatascience.com/dont-overfit-ii-how-to-avoid-overfitting-in-your-machine-learning-and-deep-learning-models-2ff903f4b36a/)
- [Analytics Vidhya — Kaggle Don't Overfit II](https://medium.com/analytics-vidhya/kaggle-competition-dont-overfit-ii-74cf2d9deed5)
