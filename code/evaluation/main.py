"""Scoring harness entry point.

``python code/evaluation/main.py`` reads a predicted CSV and the labelled gold
CSV (``dataset/sample_claims.csv`` by default), aligns rows by
``(user_id, image_paths)``, computes every metric family in ``metrics.py`` and
prints a readable report. Only the stdlib ``csv`` module is used to read CSVs so
the harness has no dependency on the pipeline that produced the predictions.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Allow ``python code/evaluation/main.py`` to import the sibling metrics module:
# code/ must be the import root (evaluation is a package under code/), so insert
# the code/ directory, not the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation import cross_validation  # noqa: E402
from evaluation import metrics  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_GOLD_CSV = _PROJECT_ROOT / "dataset" / "sample_claims.csv"
_DEFAULT_PRED_CSV = _PROJECT_ROOT / "output.csv"

# The pair of columns that uniquely identifies a claim row across the two CSVs.
_ALIGN_KEY_COLUMNS = ("user_id", "image_paths")


def _read_rows(csv_path: str | Path) -> list[dict[str, str]]:
    """Read a CSV into a list of dict rows using the stdlib csv reader.

    Raises a clear error if the file is missing or unreadable rather than
    letting a bare OSError surface without context.
    """
    path = Path(csv_path)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"CSV not found: {path}") from error
    except OSError as error:
        raise OSError(f"failed to read CSV {path}: {error}") from error


def _align_key(row: dict[str, str]) -> tuple[str, ...]:
    """Build the alignment key for a row, tolerant of whitespace."""
    return tuple(str(row.get(column, "")).strip() for column in _ALIGN_KEY_COLUMNS)


def align_rows(
    predicted_rows: list[dict[str, str]], gold_rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Align predicted rows to gold rows by ``(user_id, image_paths)``.

    Gold drives the iteration order so the report mirrors the labelled set.
    Returns two parallel lists in matched order. Predicted rows with no gold
    counterpart are dropped (they cannot be scored); gold rows missing a
    prediction raise, because a missing prediction is a real evaluation gap the
    operator must see, not silently skip.
    """
    predicted_by_key: dict[tuple[str, ...], dict[str, str]] = {
        _align_key(row): row for row in predicted_rows
    }
    aligned_pred: list[dict[str, str]] = []
    aligned_gold: list[dict[str, str]] = []
    missing: list[tuple[str, ...]] = []

    for gold_row in gold_rows:
        key = _align_key(gold_row)
        prediction = predicted_by_key.get(key)
        if prediction is None:
            missing.append(key)
            continue
        aligned_pred.append(prediction)
        aligned_gold.append(gold_row)

    if missing:
        preview = ", ".join("|".join(key) for key in missing[:5])
        raise ValueError(
            f"{len(missing)} gold row(s) have no matching prediction (by "
            f"user_id,image_paths). First few: {preview}"
        )

    return aligned_pred, aligned_gold


def format_report(report: dict) -> str:
    """Render the metrics report dict as a human-readable plaintext block."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"EVALUATION REPORT  ({report['row_count']} rows scored)")
    lines.append("=" * 60)

    lines.append("")
    lines.append("Per-column exact-match accuracy:")
    for column, stats in report["column_accuracies"].items():
        lines.append(
            f"  {column:<28} {stats['accuracy']:.3f}  "
            f"({stats['correct']}/{stats['total']})"
        )

    lines.append("")
    lines.append("claim_status confusion (rows = gold, cols = predicted):")
    labels = metrics.CLAIM_STATUS_LABELS
    header = " " * 24 + "".join(f"{label[:12]:>14}" for label in labels)
    lines.append(header)
    confusion = report["claim_status_confusion"]
    for gold_label in labels:
        cells = "".join(
            f"{confusion[gold_label][pred_label]:>14}" for pred_label in labels
        )
        lines.append(f"  {gold_label:<22}{cells}")

    lines.append("")
    risk = report["risk_flags"]
    lines.append("risk_flags (multi-label, micro-averaged):")
    lines.append(
        f"  precision={risk['micro_precision']:.3f}  "
        f"recall={risk['micro_recall']:.3f}  f1={risk['micro_f1']:.3f}  "
        f"mean_jaccard={risk['mean_jaccard']:.3f}"
    )
    lines.append(
        f"  tp={risk['true_positives']}  fp={risk['false_positives']}  "
        f"fn={risk['false_negatives']}"
    )

    lines.append("")
    supporting = report["supporting_image_ids"]
    lines.append("supporting_image_ids (set match):")
    lines.append(
        f"  exact_match={supporting['exact_match_accuracy']:.3f}  "
        f"mean_jaccard={supporting['mean_jaccard']:.3f}"
    )

    lines.append("")
    lines.append("Per-object breakdown (grouped by gold claim_object):")
    for object_label, slice_report in report["per_object"].items():
        status = slice_report["claim_status"]["accuracy"]
        lines.append(
            f"  {object_label:<10} count={slice_report['count']:<3} "
            f"claim_status_acc={status:.3f}"
        )

    lines.append("=" * 60)
    return "\n".join(lines)


def evaluate(
    pred_csv: str | Path = _DEFAULT_PRED_CSV,
    gold_csv: str | Path = _DEFAULT_GOLD_CSV,
) -> dict:
    """Read two CSVs, align by key, compute all metrics, print the report.

    Returns the full metrics report dict so callers (tests, compare.py) can
    assert on it. Printing is a side effect for the CLI; the return value is the
    programmatic contract.
    """
    predicted_rows = _read_rows(pred_csv)
    gold_rows = _read_rows(gold_csv)
    aligned_pred, aligned_gold = align_rows(predicted_rows, gold_rows)
    report = metrics.evaluate_rows(aligned_pred, aligned_gold)
    print(format_report(report))
    head = cross_validation.headline(aligned_pred, aligned_gold)
    wilson = head["wilson_95"]
    print("")
    print("claim_status robustness (small-n; treat as directional):")
    print(
        f"  accuracy={head['claim_status_accuracy']:.3f}  "
        f"wilson95=[{wilson[0]:.2f}, {wilson[1]:.2f}]  "
        f"5fold_mean={head['fold_mean']:.3f}+/-{head['fold_std']:.3f}"
    )
    print(f"  {head['caveat']}")
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python code/evaluation/main.py [pred_csv] [gold_csv]``."""
    args = list(sys.argv[1:] if argv is None else argv)
    pred_csv = args[0] if len(args) >= 1 else _DEFAULT_PRED_CSV
    gold_csv = args[1] if len(args) >= 2 else _DEFAULT_GOLD_CSV
    try:
        evaluate(pred_csv, gold_csv)
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"evaluation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
