"""Pure scoring functions over predicted/gold output rows.

Every function here takes two equal-length lists of plain dicts (one dict per
output.csv row, keyed by the 14 column names) and returns plain dicts of numbers.
There are deliberately NO imports of the runtime pipeline (decision tree, agent,
formatter): the harness must be able to score any CSV, including ones produced by
a competitor or a different strategy, without loading model code. Keeping these
functions side-effect free also makes the report reproducible.

Column families scored here:
  - 5 single-value enum columns + 2 boolean columns: exact-match accuracy.
  - claim_status: a 3x3 confusion matrix (gold label x predicted label).
  - risk_flags: multi-label micro precision/recall/F1 and mean Jaccard over the
    semicolon-separated sets, with the literal ``none`` treated as the empty set.
  - supporting_image_ids: set exact-match accuracy and mean Jaccard, with the
    ``none`` token (used on not_enough_information rows) treated as the empty set
    so a matched none<->none pair scores as a perfect hit.
  - per-object breakdown: the same column accuracies grouped by gold claim_object.
"""

from __future__ import annotations

# The 5 single-value enum columns scored by exact match. risk_flags is the sixth
# enum vocabulary but it is multi-label, so it is scored separately via F1/Jaccard
# in ``risk_flags_scores`` rather than here.
SINGLE_VALUE_ENUM_COLUMNS: tuple[str, ...] = (
    "claim_object",
    "issue_type",
    "object_part",
    "claim_status",
    "severity",
)

# The 2 boolean columns. Compared after normalization so "True"/"TRUE"/"true" and
# "False"/"false" all collapse to a canonical token before comparison.
BOOLEAN_COLUMNS: tuple[str, ...] = ("evidence_standard_met", "valid_image")

# claim_status label space, fixed so the confusion matrix always has all 3x3 cells
# even when a label never appears in the data.
CLAIM_STATUS_LABELS: tuple[str, ...] = (
    "supported",
    "contradicted",
    "not_enough_information",
)

# Tokens that mean "empty set" in the multi-value columns.
_EMPTY_SET_TOKEN = "none"
_MULTI_VALUE_SEPARATOR = ";"
_OBJECT_LABELS: tuple[str, ...] = ("car", "laptop", "package")


def _require_aligned(predicted: list[dict], gold: list[dict]) -> None:
    """Fail loudly when the two row lists are not the same length.

    Silent truncation would corrupt every downstream metric, so this is an
    explicit error path rather than a ``zip`` that drops the tail.
    """
    if len(predicted) != len(gold):
        raise ValueError(
            "predicted and gold must have the same row count: "
            f"{len(predicted)} != {len(gold)}"
        )


def _normalize_bool(raw: str) -> str:
    """Collapse a boolean cell to a canonical lowercase token.

    Different writers emit ``true``/``True``/``TRUE``; comparing them raw would
    report spurious mismatches, so normalize before comparison.
    """
    return str(raw).strip().lower()


def _normalize_scalar(raw: str) -> str:
    """Trim and lowercase a scalar enum cell for a forgiving exact match."""
    return str(raw).strip().lower()


def _parse_set(raw: str) -> set[str]:
    """Split a semicolon-joined multi-value cell into a set of tokens.

    The literal ``none`` and blank strings both map to the empty set. Tokens are
    trimmed and lowercased so ordering and whitespace never affect set equality.
    """
    text = str(raw).strip().lower()
    if not text or text == _EMPTY_SET_TOKEN:
        return set()
    return {
        token.strip()
        for token in text.split(_MULTI_VALUE_SEPARATOR)
        if token.strip() and token.strip() != _EMPTY_SET_TOKEN
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    """Jaccard similarity, with two empty sets defined as a perfect 1.0.

    Two empty sets represent "correctly predicted nothing" (e.g. matched none
    risk_flags or NEI supporting ids), which is a perfect agreement.
    """
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def column_accuracies(predicted: list[dict], gold: list[dict]) -> dict[str, dict]:
    """Per-column exact-match accuracy for the 5 enum + 2 boolean columns.

    Returns a dict keyed by column name with ``accuracy``, ``correct`` and
    ``total`` for each. Boolean columns are normalized before comparison; enum
    columns are trimmed/lowercased.
    """
    _require_aligned(predicted, gold)
    report: dict[str, dict] = {}

    for column in SINGLE_VALUE_ENUM_COLUMNS:
        correct = sum(
            1
            for pred_row, gold_row in zip(predicted, gold)
            if _normalize_scalar(pred_row.get(column, ""))
            == _normalize_scalar(gold_row.get(column, ""))
        )
        total = len(gold)
        report[column] = {
            "accuracy": (correct / total) if total else 0.0,
            "correct": correct,
            "total": total,
        }

    for column in BOOLEAN_COLUMNS:
        correct = sum(
            1
            for pred_row, gold_row in zip(predicted, gold)
            if _normalize_bool(pred_row.get(column, ""))
            == _normalize_bool(gold_row.get(column, ""))
        )
        total = len(gold)
        report[column] = {
            "accuracy": (correct / total) if total else 0.0,
            "correct": correct,
            "total": total,
        }

    return report


def claim_status_confusion(
    predicted: list[dict], gold: list[dict]
) -> dict[str, dict[str, int]]:
    """3x3 confusion matrix for claim_status.

    Outer key is the gold label, inner key is the predicted label, so
    ``matrix[gold][pred]`` counts rows whose true status is ``gold`` but were
    predicted as ``pred``. Unknown/out-of-vocabulary labels are ignored for the
    matrix (they cannot land in a fixed 3x3 grid) but still count against
    accuracy in ``column_accuracies``.
    """
    _require_aligned(predicted, gold)
    matrix: dict[str, dict[str, int]] = {
        gold_label: {pred_label: 0 for pred_label in CLAIM_STATUS_LABELS}
        for gold_label in CLAIM_STATUS_LABELS
    }
    for pred_row, gold_row in zip(predicted, gold):
        gold_label = _normalize_scalar(gold_row.get("claim_status", ""))
        pred_label = _normalize_scalar(pred_row.get("claim_status", ""))
        if gold_label in matrix and pred_label in matrix[gold_label]:
            matrix[gold_label][pred_label] += 1
    return matrix


def _multi_label_scores(
    predicted: list[dict], gold: list[dict], column: str
) -> dict[str, float | int]:
    """Shared multi-label scorer for any semicolon-set column.

    Computes micro-averaged true/false positives and negatives across all rows
    (so frequent labels dominate, which matches how the rubric weighs the column)
    plus the mean per-row Jaccard. micro_f1 with no positives anywhere is defined
    as 1.0: there was nothing to get wrong.
    """
    _require_aligned(predicted, gold)
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    jaccard_sum = 0.0

    for pred_row, gold_row in zip(predicted, gold):
        pred_set = _parse_set(pred_row.get(column, ""))
        gold_set = _parse_set(gold_row.get(column, ""))
        true_positives += len(pred_set & gold_set)
        false_positives += len(pred_set - gold_set)
        false_negatives += len(gold_set - pred_set)
        jaccard_sum += _jaccard(pred_set, gold_set)

    predicted_positives = true_positives + false_positives
    actual_positives = true_positives + false_negatives
    precision = (
        true_positives / predicted_positives if predicted_positives else 1.0
    )
    recall = true_positives / actual_positives if actual_positives else 1.0
    if precision + recall == 0:
        f1 = 0.0
    elif predicted_positives == 0 and actual_positives == 0:
        # Nothing predicted and nothing expected: a perfect, trivial agreement.
        f1 = 1.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    row_count = len(gold)
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1,
        "mean_jaccard": (jaccard_sum / row_count) if row_count else 1.0,
    }


def risk_flags_scores(
    predicted: list[dict], gold: list[dict]
) -> dict[str, float | int]:
    """Multi-label scoring for the risk_flags column (semicolon-separated set).

    ``none`` is treated as the empty set. Returns micro precision/recall/F1 and
    mean Jaccard. Exact set agreement yields F1 and Jaccard of 1.0.
    """
    return _multi_label_scores(predicted, gold, "risk_flags")


def supporting_image_ids_scores(
    predicted: list[dict], gold: list[dict]
) -> dict[str, float | int]:
    """Set scoring for supporting_image_ids.

    Returns ``exact_match_accuracy`` (fraction of rows whose id set matches
    exactly, with none<->none counted as a match) and ``mean_jaccard``. On
    not_enough_information rows both sides carry ``none`` (the empty set), so a
    matched none<->none pair is a perfect hit, while ``none`` vs a non-empty set
    is a clean miss.
    """
    _require_aligned(predicted, gold)
    if not gold:
        return {"exact_match_accuracy": 1.0, "mean_jaccard": 1.0}

    exact_hits = 0
    jaccard_sum = 0.0
    for pred_row, gold_row in zip(predicted, gold):
        pred_set = _parse_set(pred_row.get("supporting_image_ids", ""))
        gold_set = _parse_set(gold_row.get("supporting_image_ids", ""))
        if pred_set == gold_set:
            exact_hits += 1
        jaccard_sum += _jaccard(pred_set, gold_set)

    row_count = len(gold)
    return {
        "exact_match_accuracy": exact_hits / row_count,
        "mean_jaccard": jaccard_sum / row_count,
    }


def per_object_breakdown(
    predicted: list[dict], gold: list[dict]
) -> dict[str, dict]:
    """Per-object (car/laptop/package) slice of the enum/boolean accuracies.

    Rows are grouped by the gold ``claim_object`` so the breakdown reflects what
    each object type truly is, not what the model guessed. Object types absent
    from the data are omitted from the result.
    """
    _require_aligned(predicted, gold)
    breakdown: dict[str, dict] = {}

    for object_label in _OBJECT_LABELS:
        pred_slice = [
            pred_row
            for pred_row, gold_row in zip(predicted, gold)
            if _normalize_scalar(gold_row.get("claim_object", "")) == object_label
        ]
        gold_slice = [
            gold_row
            for gold_row in gold
            if _normalize_scalar(gold_row.get("claim_object", "")) == object_label
        ]
        if not gold_slice:
            continue
        slice_report = column_accuracies(pred_slice, gold_slice)
        slice_report["count"] = len(gold_slice)
        breakdown[object_label] = slice_report

    return breakdown


def evaluate_rows(predicted: list[dict], gold: list[dict]) -> dict:
    """Aggregate every metric family into one report dict.

    This is the single entry point the scoring harness and the strategy
    comparison call. It returns a nested dict that is trivially JSON-serializable
    so the report can be printed or persisted unchanged.
    """
    _require_aligned(predicted, gold)
    return {
        "row_count": len(gold),
        "column_accuracies": column_accuracies(predicted, gold),
        "claim_status_confusion": claim_status_confusion(predicted, gold),
        "risk_flags": risk_flags_scores(predicted, gold),
        "supporting_image_ids": supporting_image_ids_scores(predicted, gold),
        "per_object": per_object_breakdown(predicted, gold),
    }
