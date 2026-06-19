"""Tests for the cross-validation / variance reporting module.

These assert the properties the research methodology depends on: Wilson CI
matches a known reference value, stratified folds are a real partition that
preserves class balance, fold_variance yields one accuracy per fold, LOOCV
matches a hand-computed example, and the headline always carries both a
confidence interval and the small-n caveat. conftest.py puts code/ on sys.path,
so we import the bare top-level package.
"""

from __future__ import annotations

import pytest

from evaluation import cross_validation
from evaluation import metrics


def _row(user_id: str, image_paths: str, claim_status: str) -> dict:
    """Build a minimal row dict with just the fields this module reads."""
    return {
        "user_id": user_id,
        "image_paths": image_paths,
        "claim_status": claim_status,
    }


# --- wilson_interval ---------------------------------------------------------


def test_wilson_interval_known_value():
    """5 of 6 successes -> roughly (0.44, 0.97) per the research CI table."""
    lower, upper = cross_validation.wilson_interval(5, 6)
    assert lower == pytest.approx(0.44, abs=0.03)
    assert upper == pytest.approx(0.97, abs=0.03)


def test_wilson_interval_bounds_are_valid_probabilities():
    """The interval always stays inside [0, 1], even at the 0% and 100% edges."""
    for successes, n in [(0, 20), (20, 20), (1, 20), (19, 20)]:
        lower, upper = cross_validation.wilson_interval(successes, n)
        assert 0.0 <= lower <= upper <= 1.0


def test_wilson_interval_handles_zero_n():
    """n=0 returns the degenerate (0.0, 0.0) instead of dividing by zero."""
    assert cross_validation.wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_interval_rejects_bad_inputs():
    """Out-of-range successes and negative n are explicit errors, not silent."""
    with pytest.raises(ValueError):
        cross_validation.wilson_interval(7, 6)
    with pytest.raises(ValueError):
        cross_validation.wilson_interval(-1, 6)
    with pytest.raises(ValueError):
        cross_validation.wilson_interval(0, -1)


# --- stratified_fold_indices -------------------------------------------------


def test_stratified_folds_are_a_partition():
    """Every index appears exactly once across all folds (a true partition)."""
    labels = ["a"] * 13 + ["b"] * 5 + ["c"] * 2
    folds = cross_validation.stratified_fold_indices(labels, k=5, seed=0)
    assert len(folds) == 5
    flattened = sorted(index for fold in folds for index in fold)
    assert flattened == list(range(len(labels)))


def test_stratified_folds_preserve_class_counts():
    """Pooling the folds back together preserves the exact per-class counts."""
    labels = ["supported"] * 13 + ["contradicted"] * 5 + ["nei"] * 2
    folds = cross_validation.stratified_fold_indices(labels, k=5, seed=0)

    pooled: dict[str, int] = {}
    for fold in folds:
        for index in fold:
            pooled[labels[index]] = pooled.get(labels[index], 0) + 1
    assert pooled == {"supported": 13, "contradicted": 5, "nei": 2}


def test_stratified_folds_spread_majority_class_evenly():
    """A class of 13 over 5 folds lands 2-3 per fold, never all in one fold."""
    labels = ["a"] * 13 + ["b"] * 5 + ["c"] * 2
    folds = cross_validation.stratified_fold_indices(labels, k=5, seed=0)
    per_fold_a = [sum(1 for i in fold if labels[i] == "a") for fold in folds]
    assert max(per_fold_a) - min(per_fold_a) <= 1
    assert sum(per_fold_a) == 13


def test_stratified_folds_are_deterministic():
    """Same (labels, k, seed) gives byte-identical folds across runs."""
    labels = ["a"] * 13 + ["b"] * 5 + ["c"] * 2
    first = cross_validation.stratified_fold_indices(labels, k=5, seed=0)
    second = cross_validation.stratified_fold_indices(labels, k=5, seed=0)
    assert first == second


def test_stratified_folds_reject_bad_k():
    """k below 1 is an explicit error."""
    with pytest.raises(ValueError):
        cross_validation.stratified_fold_indices(["a", "b"], k=0)


# --- fold_variance -----------------------------------------------------------


def test_fold_variance_returns_k_accuracies():
    """A 20-row, perfectly-predicted set yields 5 fold accuracies, all 1.0."""
    statuses = ["supported"] * 13 + ["contradicted"] * 5 + ["nei"] * 2
    gold = [_row(f"u{i}", f"img{i}.png", s) for i, s in enumerate(statuses)]
    pred = [dict(row) for row in gold]  # perfect predictions

    result = cross_validation.fold_variance(pred, gold, k=5, seed=0)
    assert result["k"] == 5
    assert len(result["fold_accuracies"]) == 5
    assert result["mean"] == pytest.approx(1.0)
    assert result["std"] == pytest.approx(0.0)
    assert result["min"] == pytest.approx(1.0)
    assert result["max"] == pytest.approx(1.0)


def test_fold_variance_reflects_errors_in_spread():
    """Introducing wrong rows pulls the mean below 1.0 and widens min/max."""
    statuses = ["supported"] * 13 + ["contradicted"] * 5 + ["nei"] * 2
    gold = [_row(f"u{i}", f"img{i}.png", s) for i, s in enumerate(statuses)]
    pred = [dict(row) for row in gold]
    # Flip a handful of predictions to wrong labels.
    for i in (0, 1, 2, 3):
        pred[i]["claim_status"] = "contradicted" if statuses[i] != "contradicted" else "supported"

    result = cross_validation.fold_variance(pred, gold, k=5, seed=0)
    assert result["mean"] < 1.0
    assert result["min"] <= result["mean"] <= result["max"]


def test_fold_variance_rejects_misaligned_lengths():
    """Unequal row counts break the alignment contract and must raise."""
    with pytest.raises(ValueError):
        cross_validation.fold_variance(
            [_row("u0", "i0", "supported")],
            [_row("u0", "i0", "supported"), _row("u1", "i1", "contradicted")],
        )


# --- loocv_report ------------------------------------------------------------


def test_loocv_report_matches_hand_computed_example():
    """A 4-row example with exactly 3 hits gives accuracy 0.75 and 3 records."""
    gold = [
        _row("u0", "a.png", "supported"),
        _row("u1", "b.png", "contradicted"),
        _row("u2", "c.png", "not_enough_information"),
        _row("u3", "d.png", "supported"),
    ]
    pred = [
        _row("u0", "a.png", "supported"),       # hit
        _row("u1", "b.png", "supported"),       # miss
        _row("u2", "c.png", "not_enough_information"),  # hit
        _row("u3", "d.png", "supported"),       # hit
    ]

    report = cross_validation.loocv_report(pred, gold)
    assert report["total"] == 4
    assert report["correct"] == 3
    assert report["accuracy"] == pytest.approx(0.75)
    assert len(report["rows"]) == 4
    # The second row is the only miss, and it is traceable by its key.
    assert [r["correct"] for r in report["rows"]] == [True, False, True, True]
    assert report["rows"][1]["key"] == "u1|b.png"
    assert report["rows"][1]["gold"] == "contradicted"
    assert report["rows"][1]["pred"] == "supported"


def test_loocv_report_carries_wilson_interval():
    """The overall accuracy ships its Wilson CI, and it brackets the estimate."""
    gold = [_row(f"u{i}", f"i{i}", "supported") for i in range(20)]
    pred = [dict(row) for row in gold]
    pred[0]["claim_status"] = "contradicted"  # 19/20 correct

    report = cross_validation.loocv_report(pred, gold)
    assert report["accuracy"] == pytest.approx(19 / 20)
    lower, upper = report["wilson_95"]
    assert lower <= report["accuracy"] <= upper
    assert (lower, upper) == cross_validation.wilson_interval(19, 20)


def test_loocv_report_normalizes_case_and_whitespace():
    """Gold ' Supported ' matches predicted 'supported' (trim + lowercase)."""
    gold = [_row("u0", "a.png", " Supported ")]
    pred = [_row("u0", "a.png", "supported")]
    report = cross_validation.loocv_report(pred, gold)
    assert report["correct"] == 1


# --- headline ----------------------------------------------------------------


def test_headline_includes_ci_and_caveat():
    """The headline always pairs a CI, a fold mean/std, and the n=20 caveat."""
    statuses = ["supported"] * 13 + ["contradicted"] * 5 + ["nei"] * 2
    gold = [_row(f"u{i}", f"img{i}.png", s) for i, s in enumerate(statuses)]
    pred = [dict(row) for row in gold]
    pred[0]["claim_status"] = "contradicted"  # one miss

    head = cross_validation.headline(pred, gold, k=5, seed=0)
    assert head["row_count"] == 20
    assert head["claim_status_accuracy"] == pytest.approx(19 / 20)

    lower, upper = head["wilson_95"]
    assert 0.0 <= lower <= head["claim_status_accuracy"] <= upper <= 1.0

    assert "fold_mean" in head and "fold_std" in head
    assert head["k"] == 5
    assert isinstance(head["caveat"], str)
    assert "n=20" in head["caveat"]


def test_headline_accuracy_agrees_with_loocv():
    """Headline accuracy equals loocv_report accuracy (deterministic pipeline)."""
    statuses = ["supported"] * 13 + ["contradicted"] * 5 + ["nei"] * 2
    gold = [_row(f"u{i}", f"img{i}.png", s) for i, s in enumerate(statuses)]
    pred = [dict(row) for row in gold]
    for i in (0, 5, 18):
        pred[i]["claim_status"] = "not_enough_information"

    head = cross_validation.headline(pred, gold)
    loocv = cross_validation.loocv_report(pred, gold)
    assert head["claim_status_accuracy"] == pytest.approx(loocv["accuracy"])


def test_module_reuses_claim_status_label_space():
    """Sanity tie-in: metrics' label space is the vocabulary we score against."""
    assert "not_enough_information" in metrics.CLAIM_STATUS_LABELS
