"""Tests for the evaluation metrics (pure functions over predicted/gold dicts).

Written test-first. The metrics module never imports runtime pipeline files; it
operates on plain dicts that mirror an output.csv row, so these fixtures are
hand-built dicts with the exact 14 column keys.
"""

from __future__ import annotations

from evaluation import metrics


def _row(**overrides: object) -> dict[str, str]:
    """Build a full 14-column output row with sensible defaults, then override.

    Defaults describe a clean ``supported`` car-dent row so individual tests
    only have to state the field under test.
    """
    base: dict[str, str] = {
        "user_id": "user_001",
        "image_paths": "images/sample/case_001/img_1.jpg",
        "user_claim": "rear bumper dent",
        "claim_object": "car",
        "evidence_standard_met": "true",
        "evidence_standard_met_reason": "part visible",
        "risk_flags": "none",
        "issue_type": "dent",
        "object_part": "rear_bumper",
        "claim_status": "supported",
        "claim_status_justification": "dent visible on rear bumper",
        "supporting_image_ids": "img_1",
        "valid_image": "true",
        "severity": "medium",
    }
    base.update({key: str(value) for key, value in overrides.items()})
    return base


# --------------------------------------------------------------------------- #
# Single-value enum + boolean exact-match accuracy
# --------------------------------------------------------------------------- #


def test_enum_columns_are_the_five_single_value_enums() -> None:
    assert metrics.SINGLE_VALUE_ENUM_COLUMNS == (
        "claim_object",
        "issue_type",
        "object_part",
        "claim_status",
        "severity",
    )


def test_boolean_columns_are_the_two_bools() -> None:
    assert metrics.BOOLEAN_COLUMNS == ("evidence_standard_met", "valid_image")


def test_perfect_match_gives_accuracy_one_for_every_column() -> None:
    pred = [_row(), _row(claim_object="laptop", object_part="screen")]
    gold = [_row(), _row(claim_object="laptop", object_part="screen")]

    report = metrics.column_accuracies(pred, gold)

    for column in metrics.SINGLE_VALUE_ENUM_COLUMNS + metrics.BOOLEAN_COLUMNS:
        assert report[column]["accuracy"] == 1.0
        assert report[column]["correct"] == report[column]["total"]


def test_single_column_mismatch_lowers_only_that_columns_accuracy() -> None:
    pred = [_row(severity="low"), _row(severity="high")]
    gold = [_row(severity="medium"), _row(severity="high")]

    report = metrics.column_accuracies(pred, gold)

    assert report["severity"]["accuracy"] == 0.5
    assert report["severity"]["correct"] == 1
    assert report["severity"]["total"] == 2
    # Other enum columns are untouched.
    assert report["claim_object"]["accuracy"] == 1.0


def test_boolean_normalization_treats_true_and_TRUE_as_equal() -> None:
    pred = [_row(valid_image="TRUE", evidence_standard_met="False")]
    gold = [_row(valid_image="true", evidence_standard_met="false")]

    report = metrics.column_accuracies(pred, gold)

    assert report["valid_image"]["accuracy"] == 1.0
    assert report["evidence_standard_met"]["accuracy"] == 1.0


# --------------------------------------------------------------------------- #
# claim_status 3x3 confusion matrix
# --------------------------------------------------------------------------- #


def test_claim_status_confusion_matrix_counts_gold_by_predicted() -> None:
    pred = [
        _row(claim_status="supported"),
        _row(claim_status="contradicted"),
        _row(claim_status="supported"),  # gold says contradicted -> off-diagonal
        _row(claim_status="not_enough_information"),
    ]
    gold = [
        _row(claim_status="supported"),
        _row(claim_status="contradicted"),
        _row(claim_status="contradicted"),
        _row(claim_status="not_enough_information"),
    ]

    confusion = metrics.claim_status_confusion(pred, gold)

    # Diagonal: two exact hits (supported, NEI) and one contradicted hit.
    assert confusion["supported"]["supported"] == 1
    assert confusion["contradicted"]["contradicted"] == 1
    assert confusion["not_enough_information"]["not_enough_information"] == 1
    # The miss: gold=contradicted but predicted=supported.
    assert confusion["contradicted"]["supported"] == 1
    # Every other cell is zero.
    assert confusion["supported"]["contradicted"] == 0
    assert confusion["not_enough_information"]["supported"] == 0


# --------------------------------------------------------------------------- #
# risk_flags multi-label F1 / Jaccard (semicolon sets)
# --------------------------------------------------------------------------- #


def test_risk_flags_exact_set_match_is_f1_one() -> None:
    pred = [_row(risk_flags="user_history_risk;manual_review_required")]
    gold = [_row(risk_flags="manual_review_required;user_history_risk")]

    result = metrics.risk_flags_scores(pred, gold)

    assert result["micro_f1"] == 1.0
    assert result["mean_jaccard"] == 1.0


def test_risk_flags_partial_overlap_computes_micro_f1_and_jaccard() -> None:
    # Predicted = {a, b}; Gold = {b, c}. Intersection {b}.
    # TP=1, FP=1 (a), FN=1 (c). Precision=1/2, Recall=1/2, F1=1/2.
    # Jaccard = |{b}| / |{a,b,c}| = 1/3.
    pred = [_row(risk_flags="claim_mismatch;wrong_object")]
    gold = [_row(risk_flags="wrong_object;non_original_image")]

    result = metrics.risk_flags_scores(pred, gold)

    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["micro_precision"] == 0.5
    assert result["micro_recall"] == 0.5
    assert result["micro_f1"] == 0.5
    assert abs(result["mean_jaccard"] - (1.0 / 3.0)) < 1e-9


def test_risk_flags_none_token_is_treated_as_empty_set() -> None:
    # Both "none" -> empty vs empty. Convention: a matched empty pair is a
    # perfect prediction (Jaccard 1.0) and contributes no TP/FP/FN.
    pred = [_row(risk_flags="none")]
    gold = [_row(risk_flags="none")]

    result = metrics.risk_flags_scores(pred, gold)

    assert result["true_positives"] == 0
    assert result["false_positives"] == 0
    assert result["false_negatives"] == 0
    assert result["mean_jaccard"] == 1.0
    # micro_f1 has no positives anywhere -> defined as 1.0 (nothing to get wrong).
    assert result["micro_f1"] == 1.0


def test_risk_flags_predicting_flags_against_none_is_all_false_positives() -> None:
    pred = [_row(risk_flags="blurry_image;wrong_angle")]
    gold = [_row(risk_flags="none")]

    result = metrics.risk_flags_scores(pred, gold)

    assert result["true_positives"] == 0
    assert result["false_positives"] == 2
    assert result["false_negatives"] == 0
    assert result["micro_f1"] == 0.0
    assert result["mean_jaccard"] == 0.0


# --------------------------------------------------------------------------- #
# supporting_image_ids set match (none <-> NEI)
# --------------------------------------------------------------------------- #


def test_supporting_image_ids_exact_subset_match() -> None:
    pred = [_row(supporting_image_ids="img_2;img_1")]
    gold = [_row(supporting_image_ids="img_1;img_2")]

    result = metrics.supporting_image_ids_scores(pred, gold)

    assert result["exact_match_accuracy"] == 1.0
    assert result["mean_jaccard"] == 1.0


def test_supporting_image_ids_none_matches_none_for_nei_rows() -> None:
    # NEI rows carry supporting_image_ids = "none" on both sides; they must be
    # scored as an exact match, not as a mismatch from a missing set.
    pred = [_row(claim_status="not_enough_information", supporting_image_ids="none")]
    gold = [_row(claim_status="not_enough_information", supporting_image_ids="none")]

    result = metrics.supporting_image_ids_scores(pred, gold)

    assert result["exact_match_accuracy"] == 1.0
    assert result["mean_jaccard"] == 1.0


def test_supporting_image_ids_none_vs_ids_is_a_mismatch() -> None:
    pred = [_row(supporting_image_ids="none")]
    gold = [_row(supporting_image_ids="img_1")]

    result = metrics.supporting_image_ids_scores(pred, gold)

    assert result["exact_match_accuracy"] == 0.0
    assert result["mean_jaccard"] == 0.0


def test_supporting_image_ids_partial_overlap_jaccard() -> None:
    # pred {img_1, img_2}, gold {img_2, img_3}: intersection 1, union 3.
    pred = [_row(supporting_image_ids="img_1;img_2")]
    gold = [_row(supporting_image_ids="img_2;img_3")]

    result = metrics.supporting_image_ids_scores(pred, gold)

    assert result["exact_match_accuracy"] == 0.0
    assert abs(result["mean_jaccard"] - (1.0 / 3.0)) < 1e-9


# --------------------------------------------------------------------------- #
# per-object (car/laptop/package) breakdown
# --------------------------------------------------------------------------- #


def test_per_object_breakdown_groups_rows_by_gold_claim_object() -> None:
    pred = [
        _row(claim_object="car", claim_status="supported"),
        _row(claim_object="laptop", claim_status="supported"),
        _row(claim_object="laptop", claim_status="contradicted"),
    ]
    gold = [
        _row(claim_object="car", claim_status="supported"),
        _row(claim_object="laptop", claim_status="supported"),
        _row(claim_object="laptop", claim_status="supported"),  # miss
    ]

    breakdown = metrics.per_object_breakdown(pred, gold)

    assert breakdown["car"]["count"] == 1
    assert breakdown["laptop"]["count"] == 2
    assert breakdown["car"]["claim_status"]["accuracy"] == 1.0
    # laptop: one of two claim_status predictions is correct.
    assert breakdown["laptop"]["claim_status"]["accuracy"] == 0.5
    assert "package" not in breakdown  # no package rows -> not present


def test_evaluate_rows_aggregates_every_metric_family() -> None:
    pred = [
        _row(),
        _row(claim_object="laptop", object_part="screen", severity="low"),
    ]
    gold = [
        _row(),
        _row(claim_object="laptop", object_part="screen", severity="low"),
    ]

    report = metrics.evaluate_rows(pred, gold)

    assert report["row_count"] == 2
    assert "column_accuracies" in report
    assert "claim_status_confusion" in report
    assert "risk_flags" in report
    assert "supporting_image_ids" in report
    assert "per_object" in report
    assert report["column_accuracies"]["claim_object"]["accuracy"] == 1.0


def test_mismatched_lengths_raise_value_error() -> None:
    import pytest

    with pytest.raises(ValueError):
        metrics.column_accuracies([_row()], [_row(), _row()])
