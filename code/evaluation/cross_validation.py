"""Cross-validation and variance reporting for the n=20 calibration set.

WHY this module exists, and what it deliberately does NOT do:

The system under test is a deterministic rule/prompt pipeline, not a trainable
model. There are no weights to fit. So the "folds" here are NOT for learning a
parameter on a train split and scoring a held-out split; the same row always
produces the same prediction regardless of which fold it lands in. The folds
exist purely for VARIANCE REPORTING and per-row inspection: how much does the
headline claim_status accuracy wobble when you reslice the 20 rows into 5
stratified groups? That wobble, plus a Wilson confidence interval, is the honest
uncertainty band that research/08_eval_methodology.md mandates we report instead
of a bare percentage.

The research conclusion (research/08_eval_methodology.md) is the contract here:

  * LOOCV is the working signal. Because the pipeline is deterministic per row,
    leave-one-out reduces to "is each row's claim_status correct?" across all 20
    rows: training on the other 19 changes nothing, so the held-out prediction is
    just the row's own prediction. We therefore implement LOOCV as per-row
    correctness with an overall accuracy + Wilson CI, plus the per-row records
    that are the highest-value artifact for error clustering at this n.
  * Stratified 5-fold is the honest headline variance. It preserves the class
    balance (13/5/2 for claim_status) so each fold is representative, and the
    per-fold accuracy spread (mean / population std / min / max) is the stability
    proof.
  * Wilson score intervals carry the uncertainty, because the normal (Wald)
    approximation has wrong coverage below a few hundred points.
  * Every headline must ship the small-n caveat string so no reader mistakes a
    point estimate for a forecast.

Stdlib only (math, random, statistics): no numpy/scipy, so the harness stays
dependency-free and the numbers are reproducible from a fixed seed. Rows are the
same plain dicts the rest of code/evaluation uses, and alignment by
(user_id, image_paths) is the caller's job (see evaluation/main.align_rows), so
here we assume pred_rows[i] corresponds to gold_rows[i].
"""

from __future__ import annotations

import math
import random
import statistics

# The claim_status label compared for correctness. We compare this one field
# because it is the rubric's primary verdict; the rest of the multi-output
# metrics live in metrics.py and are out of scope for variance reporting.
_CLAIM_STATUS_FIELD = "claim_status"

# Columns that identify a row, reused only to build a stable human-readable key
# for the per-row LOOCV records (so a miss can be traced back to its source row).
_KEY_COLUMNS = ("user_id", "image_paths")

# Default headline confidence level. 1.96 is the two-sided 95% normal quantile,
# matching the "Wilson 95% CI" the research report requires on every number.
_DEFAULT_Z = 1.96

# The one-line caveat the research report requires on every headline, so a reader
# never mistakes a point estimate at n=20 for a precise forecast.
_SMALL_N_CAVEAT = (
    "n=20 with rare classes (2 NEI, 5 contradicted): no point estimate is "
    "precise to better than roughly +/-15-25 points. These numbers are a "
    "regression guard against rule breakage, not a forecast of test accuracy."
)


def wilson_interval(successes: int, n: int, z: float = _DEFAULT_Z) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    WHY Wilson and not the textbook Wald (normal) interval: below a few hundred
    samples the Wald interval has badly wrong coverage and can even leave [0, 1]
    near 0% or 100% accuracy. The Wilson score interval stays inside [0, 1] and
    keeps reasonable coverage down to n of about 10, which is the regime this
    whole module lives in (research/08_eval_methodology.md).

    Args:
        successes: number of correct outcomes (0 <= successes <= n).
        n: number of trials.
        z: standard-normal quantile for the confidence level (1.96 => 95%).

    Returns:
        (lower, upper) bounds, both clamped into [0.0, 1.0].

    Raises:
        ValueError: if n is negative, successes is out of [0, n], or z < 0.

    The n == 0 case returns (0.0, 0.0): with no trials there is no information,
    so we report a degenerate point rather than dividing by zero. Callers that
    care about "empty" should check n before reading the interval.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    if z < 0:
        raise ValueError(f"z must be non-negative, got {z}")
    if successes < 0 or successes > n:
        raise ValueError(f"successes must be in [0, {n}], got {successes}")
    if n == 0:
        return (0.0, 0.0)

    proportion = successes / n
    z_squared = z * z
    denominator = 1.0 + z_squared / n
    center = proportion + z_squared / (2.0 * n)
    margin = z * math.sqrt(proportion * (1.0 - proportion) / n + z_squared / (4.0 * n * n))
    lower = (center - margin) / denominator
    upper = (center + margin) / denominator
    # Floating-point error can push a bound a hair outside [0, 1]; clamp so the
    # reported interval is always a valid probability range.
    return (max(0.0, lower), min(1.0, upper))


def stratified_fold_indices(labels: list[str], k: int = 5, seed: int = 0) -> list[list[int]]:
    """Partition row indices into k stratified folds preserving class balance.

    WHY stratify: at n=20 with a 13/5/2 claim_status split, a naive random split
    routinely strands a whole minority class in one fold, making that fold's
    accuracy meaningless. Stratifying spreads each class as evenly as possible
    across folds so every fold is a representative miniature of the whole set,
    which is the only way the per-fold variance is an honest stability signal.

    WHY a fixed seeded shuffle (random.Random(seed)) and not random.random() or
    time-based seeding: the report must be reproducible. The same rows must land
    in the same folds on every run so a rule change is attributable to the change,
    not to a reshuffle. We deal each class's shuffled members round-robin into the
    folds, rotating the starting fold per class so the remainders do not all pile
    onto fold 0.

    Args:
        labels: one label per row; labels[i] is the stratification class of row i.
        k: number of folds (clamped to at most len(labels); must be >= 1).
        seed: fixed seed for the deterministic shuffle.

    Returns:
        A list of k lists of row indices. Every index in range(len(labels))
        appears in exactly one fold (a partition). Folds may differ in size by at
        most one within a class, which is the natural stratified balance.

    Raises:
        ValueError: if k < 1.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if not labels:
        return [[] for _ in range(k)]
    # Never create more folds than rows: empty folds would make per-fold accuracy
    # undefined and inflate the apparent variance with meaningless zeros.
    effective_k = min(k, len(labels))

    rng = random.Random(seed)

    # Group row indices by their label so each class is dealt independently.
    by_label: dict[str, list[int]] = {}
    for index, label in enumerate(labels):
        by_label.setdefault(label, []).append(index)

    folds: list[list[int]] = [[] for _ in range(effective_k)]
    # Iterate classes in a stable (sorted) order so the assignment is fully
    # determined by (labels, k, seed) and not by dict insertion quirks.
    for offset, label in enumerate(sorted(by_label)):
        members = by_label[label]
        rng.shuffle(members)
        # Rotate the starting fold per class so leftover members of small classes
        # do not all accumulate in fold 0, keeping fold sizes balanced overall.
        for position, index in enumerate(members):
            fold_index = (position + offset) % effective_k
            folds[fold_index].append(index)
    return folds


def _row_key(row: dict) -> str:
    """Build a stable, human-readable key for a row from its id columns.

    Used only to label per-row LOOCV records so a miss is traceable to its source
    row. Falls back to a blank-joined key when the id columns are absent.
    """
    return "|".join(str(row.get(column, "")).strip() for column in _KEY_COLUMNS)


def _status(row: dict) -> str:
    """Normalized claim_status of a row (trimmed, lowercased) for comparison.

    Mirrors metrics._normalize_scalar so "Supported"/" supported " compare equal
    to "supported"; we keep a local copy rather than import a private helper.
    """
    return str(row.get(_CLAIM_STATUS_FIELD, "")).strip().lower()


def _require_aligned(pred_rows: list[dict], gold_rows: list[dict]) -> None:
    """Fail loudly when the two row lists are not the same length.

    Alignment is the caller's contract (pred_rows[i] <-> gold_rows[i]); a length
    mismatch means that contract is broken, and silently zipping would drop the
    tail and corrupt every metric. So this is an explicit error path.
    """
    if len(pred_rows) != len(gold_rows):
        raise ValueError(
            "pred_rows and gold_rows must have the same length: "
            f"{len(pred_rows)} != {len(gold_rows)}"
        )


def _accuracy(pred_rows: list[dict], gold_rows: list[dict]) -> tuple[int, int]:
    """Count claim_status hits over a parallel pair of row lists.

    Returns (correct, total). Centralized so LOOCV, fold accuracy, and the
    headline all agree on exactly what "correct" means.
    """
    correct = sum(
        1
        for pred_row, gold_row in zip(pred_rows, gold_rows)
        if _status(pred_row) == _status(gold_row)
    )
    return correct, len(gold_rows)


def fold_variance(
    pred_rows: list[dict], gold_rows: list[dict], k: int = 5, seed: int = 0
) -> dict:
    """Stratified k-fold claim_status accuracy spread for honest variance.

    WHY this is variance reporting, not training: the pipeline is deterministic,
    so a fold's "held-out" accuracy is just the accuracy of its own rows; there is
    no fitted model to score. The value is the SPREAD of those per-fold
    accuracies. If the folds disagree wildly, the headline number is fragile; if
    they cluster, it is stable. We report mean, population std, min, and max so a
    reader can see that stability directly (research/08 requires min/max/std).

    Population std (statistics.pstdev), not sample std: these k folds ARE the
    whole partition we are describing, not a sample drawn from a larger pool, so
    the population spread is the honest descriptor. A single fold yields std 0.0.

    Args:
        pred_rows: predicted rows, aligned to gold_rows by the caller.
        gold_rows: gold rows; their claim_status drives stratification.
        k: requested number of folds.
        seed: fixed seed for the reproducible stratified split.

    Returns:
        {
          "k": <actual fold count used>,
          "seed": <seed>,
          "fold_accuracies": [float, ...],
          "fold_sizes": [int, ...],
          "mean": float, "std": float, "min": float, "max": float,
        }

    Raises:
        ValueError: if the two row lists differ in length, or k < 1.
    """
    _require_aligned(pred_rows, gold_rows)
    if not gold_rows:
        # No rows means no folds and no variance to report; return an explicit
        # empty shape rather than dividing by zero downstream.
        return {
            "k": 0,
            "seed": seed,
            "fold_accuracies": [],
            "fold_sizes": [],
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
        }

    gold_labels = [_status(row) for row in gold_rows]
    folds = stratified_fold_indices(gold_labels, k=k, seed=seed)

    fold_accuracies: list[float] = []
    fold_sizes: list[int] = []
    for fold in folds:
        if not fold:
            # Skip empty folds (possible only if k > row count was requested);
            # an empty fold has no defined accuracy and would distort the spread.
            continue
        fold_pred = [pred_rows[i] for i in fold]
        fold_gold = [gold_rows[i] for i in fold]
        correct, total = _accuracy(fold_pred, fold_gold)
        fold_accuracies.append(correct / total)
        fold_sizes.append(total)

    mean = statistics.fmean(fold_accuracies) if fold_accuracies else 0.0
    std = statistics.pstdev(fold_accuracies) if len(fold_accuracies) > 1 else 0.0
    return {
        "k": len(fold_accuracies),
        "seed": seed,
        "fold_accuracies": fold_accuracies,
        "fold_sizes": fold_sizes,
        "mean": mean,
        "std": std,
        "min": min(fold_accuracies) if fold_accuracies else 0.0,
        "max": max(fold_accuracies) if fold_accuracies else 0.0,
    }


def loocv_report(pred_rows: list[dict], gold_rows: list[dict]) -> dict:
    """Leave-one-out claim_status report for the deterministic pipeline.

    WHY LOOCV collapses to per-row correctness here: in classic LOOCV you train on
    19 rows and test on the held-out 1, repeated 20 times. But this pipeline has
    no trainable weights, so training on any subset changes nothing: the held-out
    row's prediction is identical to its standalone prediction. LOOCV therefore
    reduces to "score every row once" while keeping LOOCV's real benefit at this
    n: the 20 individual error records, which are the highest-value artifact for
    clustering failures by root cause (research/08, Layer A).

    Args:
        pred_rows: predicted rows, aligned to gold_rows by the caller.
        gold_rows: gold rows.

    Returns:
        {
          "rows": [{"key", "gold", "pred", "correct"}, ...],  # one per row
          "correct": int, "total": int,
          "accuracy": float,
          "wilson_95": (lower, upper),  # Wilson 95% CI on the accuracy
        }

    Raises:
        ValueError: if the two row lists differ in length.
    """
    _require_aligned(pred_rows, gold_rows)

    records: list[dict] = []
    correct = 0
    for pred_row, gold_row in zip(pred_rows, gold_rows):
        gold_status = _status(gold_row)
        pred_status = _status(pred_row)
        is_correct = pred_status == gold_status
        if is_correct:
            correct += 1
        records.append(
            {
                "key": _row_key(gold_row),
                "gold": gold_status,
                "pred": pred_status,
                "correct": is_correct,
            }
        )

    total = len(gold_rows)
    accuracy = (correct / total) if total else 0.0
    return {
        "rows": records,
        "correct": correct,
        "total": total,
        "accuracy": accuracy,
        "wilson_95": wilson_interval(correct, total),
    }


def headline(pred_rows: list[dict], gold_rows: list[dict], k: int = 5, seed: int = 0) -> dict:
    """One combined headline: overall accuracy, its Wilson CI, fold spread, caveat.

    WHY combine: the research report mandates that the headline never be a bare
    percentage. It must pair the point estimate with (a) its Wilson 95% interval
    so the uncertainty is visible, (b) the stratified-fold mean/std so stability
    is visible, and (c) a one-line small-n caveat so the reader cannot mistake the
    number for a forecast. This function is the single call that assembles all
    three for the report.

    The overall accuracy here is the LOOCV/per-row accuracy (identical for a
    deterministic pipeline), so the headline and loocv_report always agree.

    Args:
        pred_rows: predicted rows, aligned to gold_rows by the caller.
        gold_rows: gold rows.
        k: fold count for the variance block.
        seed: fixed seed for the reproducible fold split.

    Returns:
        {
          "row_count": int,
          "claim_status_accuracy": float,
          "wilson_95": (lower, upper),
          "fold_mean": float, "fold_std": float, "k": int,
          "caveat": str,
        }

    Raises:
        ValueError: if the two row lists differ in length, or k < 1.
    """
    _require_aligned(pred_rows, gold_rows)

    correct, total = _accuracy(pred_rows, gold_rows)
    accuracy = (correct / total) if total else 0.0
    folds = fold_variance(pred_rows, gold_rows, k=k, seed=seed)
    return {
        "row_count": total,
        "claim_status_accuracy": accuracy,
        "wilson_95": wilson_interval(correct, total),
        "fold_mean": folds["mean"],
        "fold_std": folds["std"],
        "k": folds["k"],
        "caveat": _SMALL_N_CAVEAT,
    }
