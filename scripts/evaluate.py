"""Evaluator — runs the pipeline on sample tickets and scores against ground truth.

NOT part of the deliverable. Run from repo root:
    python scripts/evaluate.py [--no-run]   # --no-run: use cached eval_output.csv

The sample_support_tickets.csv is a SEPARATE evaluation set (not in the main
support_tickets.csv). This script runs the pipeline on those 10 tickets and
compares the output to the ground-truth columns (Status, Product Area, Request Type).

Scoring rubric (4 points per ticket):
  status_match      1.0 pt  — exact match (replied / escalated)
  product_area_sim  1.0 pt  — Jaccard token overlap
  request_type_ok   1.0 pt  — exact match
  response_quality  1.0 pt  — length > 50 chars AND not a canned fallback

Saves results to scripts/eval_output.csv and scripts/eval_report.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "code"))

_SAMPLE_CSV = _REPO_ROOT / "support_tickets" / "sample_support_tickets.csv"
_EVAL_OUTPUT_CSV = _REPO_ROOT / "scripts" / "eval_output.csv"
_REPORT_JSON = _REPO_ROOT / "scripts" / "eval_report.json"

_CANNED_PREFIXES = (
    "thank you for reaching out",
    "thanks for getting in touch",
    "an internal error occurred",
)

_OUTPUT_FIELDNAMES = ["status", "product_area", "response", "justification", "request_type"]


# ── scoring ────────────────────────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    tokens_a = set(a.lower().replace("_", " ").replace("-", " ").split())
    tokens_b = set(b.lower().replace("_", " ").replace("-", " ").split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _is_canned(response: str) -> bool:
    return any(response.lower().strip().startswith(p) for p in _CANNED_PREFIXES)


def score_row(sample: dict, output: dict) -> dict:
    gt_status = (sample.get("Status") or "").strip().lower()
    gt_area = (sample.get("Product Area") or "").strip()
    gt_type = (sample.get("Request Type") or "").strip().lower()

    pred_status = (output.get("status") or "").strip().lower()
    pred_area = (output.get("product_area") or "").strip()
    pred_type = (output.get("request_type") or "").strip().lower()
    pred_response = (output.get("response") or "").strip()

    status_match = 1.0 if gt_status == pred_status else 0.0
    area_sim = _jaccard(gt_area, pred_area)
    type_match = 1.0 if gt_type == pred_type else 0.0
    # Invalid and escalated tickets legitimately get canned responses — don't penalise them
    is_canned_ok = gt_type == "invalid" or gt_status == "escalated"
    resp_quality = (
        1.0
        if len(pred_response) > 50 and (is_canned_ok or not _is_canned(pred_response))
        else 0.0
    )
    total = status_match + area_sim + type_match + resp_quality

    return {
        "subject": (sample.get("Subject") or sample.get("Issue") or "")[:60],
        "status_match": status_match,
        "area_jaccard": round(area_sim, 2),
        "type_match": type_match,
        "response_quality": resp_quality,
        "total": round(total, 2),
        "max": 4.0,
        "gt_status": gt_status,
        "pred_status": pred_status,
        "gt_area": gt_area,
        "pred_area": pred_area,
        "gt_type": gt_type,
        "pred_type": pred_type,
        "response_len": len(pred_response),
    }


# ── pipeline runner ────────────────────────────────────────────────────────────

def _run_pipeline_on_samples(samples: List[dict]) -> List[dict]:
    """Run the pipeline on sample tickets and return output rows."""
    from domain.types import TicketState  # noqa: E402
    from pipeline import PipelineFactory  # noqa: E402

    print("Loading pipeline…")
    pipeline = PipelineFactory.create()
    results: List[dict] = []

    for i, row in enumerate(samples, 1):
        ticket = (row.get("Issue") or "").strip()
        subject = (row.get("Subject") or "").strip()
        company = (row.get("Company") or "").strip()
        print(f"  [{i:02d}/{len(samples)}] {subject or ticket[:50]!r}…", end="  ", flush=True)

        state = TicketState(ticket=ticket, subject=subject, company=company)
        try:
            from pipeline import PipelineFactory as PF
            output = pipeline.run(state)
            row_out = output.to_dict()
        except Exception as exc:
            print(f"ERROR: {exc}")
            row_out = {
                "status": "escalated",
                "product_area": "error",
                "response": f"Internal error: {exc}",
                "justification": "",
                "request_type": "product_issue",
            }

        results.append(row_out)
        print(f"→ {row_out['status']}")
        if i < len(samples):
            time.sleep(1)

    return results


# ── report ─────────────────────────────────────────────────────────────────────

def evaluate(samples: List[dict], outputs: List[dict]) -> dict:
    n = min(len(samples), len(outputs))
    scores = [score_row(samples[i], outputs[i]) for i in range(n)]

    header = f"{'#':>3}  {'Subject':<38}  {'S':>4}  {'A':>4}  {'T':>4}  {'R':>4}  {'Total':>6}"
    print()
    print(header)
    print("-" * len(header))

    for i, s in enumerate(scores, 1):
        mismatch = ""
        if s["status_match"] < 1:
            mismatch += f" ✗status(gt={s['gt_status']},pred={s['pred_status']})"
        if s["type_match"] < 1:
            mismatch += f" ✗type(gt={s['gt_type']},pred={s['pred_type']})"
        print(
            f"{i:>3}  {s['subject']:<38}  "
            f"{s['status_match']:>4.1f}  "
            f"{s['area_jaccard']:>4.2f}  "
            f"{s['type_match']:>4.1f}  "
            f"{s['response_quality']:>4.1f}  "
            f"{s['total']:>6.2f}{mismatch}"
        )

    print("-" * len(header))
    total_score = sum(s["total"] for s in scores)
    max_score = sum(s["max"] for s in scores)
    print(f"Total: {total_score:.2f} / {max_score:.1f}  ({100*total_score/max_score:.1f}%)")

    report = {
        "total_score": total_score,
        "max_score": max_score,
        "pct": round(100 * total_score / max_score, 1),
        "rows": scores,
    }
    _REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport saved → {_REPORT_JSON}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate pipeline on sample ground truth")
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Skip running the pipeline; use cached eval_output.csv instead",
    )
    args = parser.parse_args()

    if not _SAMPLE_CSV.exists():
        print(f"ERROR: sample CSV not found: {_SAMPLE_CSV}", file=sys.stderr)
        return 1

    with _SAMPLE_CSV.open(encoding="utf-8") as fh:
        samples = list(csv.DictReader(fh))

    if args.no_run and _EVAL_OUTPUT_CSV.exists():
        print(f"Using cached eval output: {_EVAL_OUTPUT_CSV}")
        with _EVAL_OUTPUT_CSV.open(encoding="utf-8") as fh:
            outputs = list(csv.DictReader(fh))
    else:
        outputs = _run_pipeline_on_samples(samples)
        _EVAL_OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with _EVAL_OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_OUTPUT_FIELDNAMES)
            writer.writeheader()
            writer.writerows(outputs)
        print(f"Eval output saved → {_EVAL_OUTPUT_CSV}")

    evaluate(samples, outputs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
