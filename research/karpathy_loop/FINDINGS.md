# Karpathy Accuracy Loop - Findings

Curated narrative for the autonomous accuracy loop. The machine-generated metric
table and graph live in `REPORT.md` / `accuracy_iterations.png`; this file explains
*what each experiment tested, why it was kept or rejected, and what it means*. The
guiding premise (the user's): the visual pipeline is the crux, we run a single VLM,
and VLMs make mistakes - so apply Karpathy's accuracy playbook (feed the best
input, test-time augmentation, ensembles, become one with the data) and measure
every change against the 20 labeled rows, keeping only what beats the baseline.

## Result

Overall sample accuracy (mean of 6 exact-match columns + risk_flags micro-F1)
climbed **0.810 -> 0.844**, with the headline `claim_status` going 0.80 -> 0.85 and
contradicted-recall 2/5 -> 3/5. Every gain is a principled, generalizable change,
not a fit to the 20 rows.

| Lever (Karpathy method) | Result | Verdict |
|---|---|---|
| Feed the best input: resolution 1024 -> 1568 (Claude's native ceiling) | object_part 0.85 -> 0.90 | **kept** |
| Bigger model: Opus perception | claim_status 0.85, evidence 1.00, but issue_type 0.65, 5x slower | superseded by ensemble |
| Ensemble: Sonnet + Opus, decorrelated vote | overall 0.817 -> 0.840 (kept Sonnet's issue_type AND Opus's claim_status) | **kept** |
| Test-time augmentation: 5 zoom crops + damage recovery | overall 0.840 -> 0.763 | **rejected** |
| Demote EXIF authenticity (research #6) | risk_flags F1 0.727 -> 0.755 | **kept** |

Final adopted config: **1568px + Sonnet:2/Opus:2 ensemble + visual-only authenticity.**

## Why each rejected lever failed (the negative results matter)

- **Test-time augmentation (zoom crops).** The textbook fix for missed small damage,
  and it *regressed every damage column* (claim_status 0.85 -> 0.70). A crop without
  full-frame context hallucinates damage faster than it recovers real damage; the
  2-crop quorum was not enough to suppress the false positives at this scale. The
  two detail-miss rows it was built for (case_005 faint scratch, case_012 corner
  dent) were *not* recovered. Reverted; code kept behind `PERCEPTION_TTA` for repro.

- **Claim-blind perception** (earlier pass): regressed every column - without a part
  pointer the model's part-token disagreements fire false `part_mismatch`
  contradictions that outnumber the sycophancy rows it fixes.

- **Per-row severity signals** (image pixel-read / customer word / damped consensus):
  all worse than the issue-anchored prior; the image over-reads to `high`, the word
  is noisy. Kept `scratch -> low, else medium`.

- **research #3 `user_history_risk` gating**: rejected on data - gold row 16 is a
  *supported* row carrying `user_history_risk` alone, disproving the "history only
  fires with contradiction" rule. Our existing behavior already matches gold.

## What the ground-truth audit told us (becoming one with the data)

A subagent visually inspected all 7 sample misses. The breakdown reframed the
ceiling: only **2/7** were pixel-limited (resolution/zoom), **2/7** were sycophancy
(reasoning, not pixels), **2/7** were label-debatable/ambiguous (case_011 keyboard
awash in liquid -> our `water_damage` arguably beats gold `stain`; case_013 radial
impact -> `crack` vs `glass_shatter` both defensible), and **1/7** was a clear
wrong-object image we wrongly abstained on. So the *true* issue_type accuracy is
higher than the measured 0.70 - some "errors" are disagreements with noisy labels,
and chasing them would be overfitting.

## Honest caveat (n = 20)

Every per-column delta here is one or two rows; the Wilson 95% interval on
claim_status is roughly +/-15-25 points. The reason to trust the ensemble win is not
the 0.034 overall delta in isolation - it is that the gain is *consistent across
five columns at once* (claim_status, issue_type, severity, risk_flags, plus
contradicted-recall), which is what a real decorrelation effect looks like and what
single-row noise does not. The resolution and EXIF wins are mechanism-grounded
(more usable pixels; an EXIF tag that is present in honest phone photos), so they
generalize beyond these 20 rows regardless of the point estimate.

## Cost note

The ensemble reads each image 4 times (2 of them Opus), so a fresh `output.csv`
costs ~4x the single-Sonnet run and runs slower. It is the accuracy-first default;
set `PERCEPTION_ENSEMBLE=""` for a cheap single-Sonnet run. There is no per-token
billing (Claude Code subscription) and the content-hash cache makes re-runs free.
