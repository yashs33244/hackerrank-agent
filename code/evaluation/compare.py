"""Side-by-side comparison of two or more strategy/model output CSVs.

The contest requires comparing at least two configurations (for example
single-pass vs two-stage, or VLM-only risk_flags vs VLM + deterministic
post-processor). ``compare_strategies`` scores each named predicted CSV against
the same gold CSV and tabulates the headline metrics so the final choice for
``output.csv`` is justified by data, not vibes.
"""

from __future__ import annotations

from pathlib import Path

from evaluation import main as harness
from evaluation import metrics

# The headline scalar metrics surfaced in the side-by-side table. Each entry maps
# a display label to a function pulling the scalar out of a full metrics report.
_HEADLINE_METRICS: tuple[tuple[str, str], ...] = (
    ("claim_status_acc", "claim_status"),
    ("severity_acc", "severity"),
    ("object_part_acc", "object_part"),
    ("issue_type_acc", "issue_type"),
)


def _headline_row(report: dict) -> dict[str, float]:
    """Extract the comparable scalar metrics from one full metrics report."""
    columns = report["column_accuracies"]
    row: dict[str, float] = {
        label: columns[column]["accuracy"] for label, column in _HEADLINE_METRICS
    }
    row["evidence_standard_met_acc"] = columns["evidence_standard_met"]["accuracy"]
    row["valid_image_acc"] = columns["valid_image"]["accuracy"]
    row["risk_flags_f1"] = report["risk_flags"]["micro_f1"]
    row["risk_flags_jaccard"] = report["risk_flags"]["mean_jaccard"]
    row["supporting_ids_match"] = report["supporting_image_ids"][
        "exact_match_accuracy"
    ]
    return row


def compare_strategies(
    named_pred_csvs: dict[str, str], gold_csv: str | Path
) -> dict:
    """Score each named predicted CSV against ``gold_csv`` and tabulate them.

    ``named_pred_csvs`` maps a strategy/model name (e.g. ``"two_stage"``) to its
    output.csv path. Returns a dict with the full per-strategy reports plus a
    flat ``table`` of the headline scalar metrics for side-by-side reading.
    Requires at least two strategies, since the contest deliverable is a
    comparison.
    """
    if len(named_pred_csvs) < 2:
        raise ValueError(
            "compare_strategies needs at least 2 strategies to compare, "
            f"got {len(named_pred_csvs)}"
        )

    gold_rows = harness._read_rows(gold_csv)
    reports: dict[str, dict] = {}
    table: dict[str, dict[str, float]] = {}

    for name, pred_csv in named_pred_csvs.items():
        predicted_rows = harness._read_rows(pred_csv)
        aligned_pred, aligned_gold = harness.align_rows(predicted_rows, gold_rows)
        report = metrics.evaluate_rows(aligned_pred, aligned_gold)
        reports[name] = report
        table[name] = _headline_row(report)

    return {"reports": reports, "table": table}


def format_comparison(comparison: dict) -> str:
    """Render the comparison ``table`` as an aligned plaintext grid.

    Strategies are columns; headline metrics are rows. This is the block dropped
    into ``evaluation_report.md`` to justify the chosen configuration.
    """
    table = comparison["table"]
    strategy_names = list(table.keys())
    if not strategy_names:
        return "(no strategies to compare)"

    metric_names = list(table[strategy_names[0]].keys())
    name_width = max(len(name) for name in metric_names) + 2
    column_width = max(max(len(name) for name in strategy_names), 10) + 2

    lines: list[str] = []
    header = "metric".ljust(name_width) + "".join(
        name.rjust(column_width) for name in strategy_names
    )
    lines.append(header)
    lines.append("-" * len(header))
    for metric_name in metric_names:
        cells = "".join(
            f"{table[strategy][metric_name]:.3f}".rjust(column_width)
            for strategy in strategy_names
        )
        lines.append(metric_name.ljust(name_width) + cells)

    return "\n".join(lines)
