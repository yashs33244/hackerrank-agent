"""Render the Karpathy accuracy-loop log into a graph and a per-iteration report.

Reads ``research/karpathy_loop/results.jsonl`` (one JSON record per experiment,
written by ``score_iteration.py``) and produces:
  * ``accuracy_iterations.png`` - overall + per-column accuracy vs iteration, with
    adopted ("kept") configs marked, so the climb is visible at a glance.
  * ``REPORT.md`` - a table of every iteration, what changed, the metric vector,
    whether it was kept, and the running best.

Usage:  python code/evaluation/plot_iterations.py
"""

from __future__ import annotations

import json
from pathlib import Path

import config as pipeline_config

_LOOP_DIR = pipeline_config.REPO_ROOT / "research" / "karpathy_loop"
_RESULTS_PATH = _LOOP_DIR / "results.jsonl"
_PLOT_PATH = _LOOP_DIR / "accuracy_iterations.png"
_REPORT_PATH = _LOOP_DIR / "REPORT.md"

# Columns drawn as faint context lines; overall is drawn bold on top.
_COLUMNS: tuple[str, ...] = (
    "claim_status",
    "object_part",
    "issue_type",
    "severity",
    "valid_image",
    "evidence_standard_met",
    "risk_flags_f1",
)


def _load() -> list[dict]:
    if not _RESULTS_PATH.exists():
        return []
    return [json.loads(line) for line in _RESULTS_PATH.read_text().splitlines() if line.strip()]


def render_plot(records: list[dict]) -> None:
    """Draw overall (bold) + each tracked column (faint) against iteration index."""
    import matplotlib

    matplotlib.use("Agg")  # headless: write a file, never open a window
    import matplotlib.pyplot as plt

    iterations = [r["iteration"] for r in records]
    figure, axis = plt.subplots(figsize=(11, 6.5))

    for column in _COLUMNS:
        axis.plot(
            iterations,
            [r.get(column, None) for r in records],
            marker="o",
            linewidth=1.0,
            alpha=0.45,
            label=column,
        )
    axis.plot(
        iterations,
        [r["overall"] for r in records],
        marker="D",
        linewidth=2.8,
        color="black",
        label="OVERALL (mean)",
    )

    # Mark the adopted configs so the kept path is readable off the graph.
    for record in records:
        if record.get("kept"):
            axis.axvline(record["iteration"], color="green", linestyle=":", alpha=0.35)
        axis.annotate(
            record["name"],
            (record["iteration"], record["overall"]),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
            fontsize=7.5,
            rotation=20,
        )

    axis.set_xlabel("iteration")
    axis.set_ylabel("sample accuracy (n=20)")
    axis.set_title("Karpathy accuracy loop - per-column and overall accuracy by iteration")
    axis.set_xticks(iterations)
    axis.set_ylim(0.4, 1.02)
    axis.grid(True, alpha=0.25)
    axis.legend(loc="lower right", fontsize=8, ncol=2)
    figure.tight_layout()
    figure.savefig(_PLOT_PATH, dpi=130)
    plt.close(figure)


def render_report(records: list[dict]) -> None:
    """Write the per-iteration markdown report with a running-best column."""
    lines: list[str] = []
    lines.append("# Karpathy Accuracy Loop - Iteration Report\n")
    lines.append(
        "Each row is one experiment, measured on the 20 labeled sample rows. "
        "`overall` is the unweighted mean of the six exact-match column accuracies "
        "and the risk_flags micro-F1. `kept` marks a config adopted as the new "
        "running best. See `accuracy_iterations.png` for the trend.\n"
    )
    lines.append("![accuracy by iteration](accuracy_iterations.png)\n")

    header = (
        "| iter | name | overall | claim_status | object_part | issue_type | "
        "severity | valid_image | evidence | risk_F1 | kept | change |"
    )
    sep = "|" + "---|" * 12
    lines.append(header)
    lines.append(sep)

    best = -1.0
    for record in records:
        is_new_best = record["overall"] > best
        best = max(best, record["overall"])
        star = " *(new best)*" if is_new_best else ""
        lines.append(
            f"| {record['iteration']} | {record['name']} | "
            f"**{record['overall']:.3f}**{star} | {record['claim_status']:.3f} | "
            f"{record['object_part']:.3f} | {record['issue_type']:.3f} | "
            f"{record['severity']:.3f} | {record['valid_image']:.3f} | "
            f"{record['evidence_standard_met']:.3f} | {record['risk_flags_f1']:.3f} | "
            f"{'yes' if record.get('kept') else '-'} | {record['config']} |"
        )

    if records:
        best_record = max(records, key=lambda r: r["overall"])
        lines.append(
            f"\n**Best so far:** iter {best_record['iteration']} "
            f"({best_record['name']}) at overall **{best_record['overall']:.3f}**."
        )
    _REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    records = _load()
    if not records:
        print("no results yet; run score_iteration.py first")
        return 1
    render_plot(records)
    render_report(records)
    print(f"wrote {_PLOT_PATH} and {_REPORT_PATH} ({len(records)} iterations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
