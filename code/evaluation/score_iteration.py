"""Score one experiment's prediction CSV and append it to the iteration log.

Part of the Karpathy-style autonomous accuracy loop: each experiment (a config
variant such as a resolution bump, a model swap, test-time augmentation) writes a
prediction CSV, and this script reduces it to the headline metrics and appends one
JSON record to ``research/karpathy_loop/results.jsonl``. ``plot_iterations.py``
then renders the graph and report from that log. Usage:

    python code/evaluation/score_iteration.py <name> <config-desc> <pred.csv> [--gold P] [--kept]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import config as pipeline_config
from evaluation import metrics

# The six exact-match columns plus the risk_flags F1 form the tracked vector. The
# overall headline is their unweighted mean: a single scalar to watch climb.
_TRACKED_COLUMNS: tuple[str, ...] = (
    "claim_status",
    "object_part",
    "issue_type",
    "severity",
    "valid_image",
    "evidence_standard_met",
)

_RESULTS_PATH = pipeline_config.REPO_ROOT / "research" / "karpathy_loop" / "results.jsonl"


def _read_csv(path: str) -> list[dict]:
    import csv

    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def score(name: str, config_desc: str, pred_path: str, gold_path: str, kept: bool) -> dict:
    """Compute the tracked metric vector for one prediction CSV."""
    predicted = _read_csv(pred_path)
    gold = _read_csv(gold_path)
    columns = metrics.column_accuracies(predicted, gold)
    risk = metrics.risk_flags_scores(predicted, gold)

    record: dict[str, object] = {"name": name, "config": config_desc, "kept": kept}
    scalar_values: list[float] = []
    for column in _TRACKED_COLUMNS:
        accuracy = round(columns[column]["accuracy"], 4)
        record[column] = accuracy
        scalar_values.append(accuracy)
    record["risk_flags_f1"] = round(float(risk["micro_f1"]), 4)
    scalar_values.append(record["risk_flags_f1"])
    record["overall"] = round(sum(scalar_values) / len(scalar_values), 4)
    return record


def append_record(record: dict, results_path: Path = _RESULTS_PATH) -> int:
    """Append ``record`` (stamped with the next iteration index) to the log."""
    results_path.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        results_path.read_text(encoding="utf-8").splitlines()
        if results_path.exists()
        else []
    )
    record = {"iteration": len(existing), **record}
    with results_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record["iteration"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="short experiment name, e.g. 'res-1568'")
    parser.add_argument("config", help="one-line config description")
    parser.add_argument("pred_csv", help="path to the prediction CSV to score")
    parser.add_argument(
        "--gold",
        default=str(pipeline_config.SAMPLE_CLAIMS_CSV),
        help="gold-labeled CSV (default: dataset/sample_claims.csv)",
    )
    parser.add_argument(
        "--kept",
        action="store_true",
        help="mark this config as adopted (the new running best)",
    )
    args = parser.parse_args()

    record = score(args.name, args.config, args.pred_csv, args.gold, args.kept)
    index = append_record(record)
    flag = "KEPT" if args.kept else "tried"
    print(
        f"[iter {index}] {args.name} ({flag}): overall={record['overall']:.3f} "
        f"claim_status={record['claim_status']:.3f} object_part={record['object_part']:.3f} "
        f"issue_type={record['issue_type']:.3f} severity={record['severity']:.3f} "
        f"valid_image={record['valid_image']:.3f} risk_f1={record['risk_flags_f1']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
