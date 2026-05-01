"""Entry point — reads support_tickets.csv, runs pipeline, writes output.csv.

Usage:
    cd code
    python main.py

Output: support_tickets/output.csv (relative to repo root)
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import List

from config import settings
from domain.types import TicketState
from pipeline import PipelineFactory

_OUTPUT_FIELDNAMES = [
    "status",
    "product_area",
    "response",
    "justification",
    "request_type",
]


def _read_tickets(path: Path) -> List[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_output(rows: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_OUTPUT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    print(f"Loading pipeline…")
    pipeline = PipelineFactory.create()

    tickets = _read_tickets(settings.paths.input_csv)
    total = len(tickets)
    print(f"Processing {total} tickets…\n")

    results: List[dict] = []

    for idx, row in enumerate(tickets, start=1):
        ticket_text = (row.get("ticket") or row.get("Issue") or "").strip()
        subject = (row.get("subject") or row.get("Subject") or "").strip()
        company = (row.get("company") or row.get("Company") or "").strip()

        print(f"  [{idx:02d}/{total}] {subject or ticket_text[:60]!r}", end="  ", flush=True)

        state = TicketState(
            ticket=ticket_text,
            subject=subject,
            company=company,
        )

        try:
            output = pipeline.run(state)
            results.append(output.to_dict())
            print(f"→ {output.status}")
        except Exception as exc:
            print(f"→ ERROR: {exc}")
            results.append({
                "status": "escalated",
                "product_area": "error",
                "response": "An internal error occurred. Your ticket has been escalated.",
                "justification": f"Pipeline error: {exc}",
                "request_type": "product_issue",
            })

        # Throttle to stay under Gemini free-tier rate limits
        if idx < total:
            time.sleep(1)

    _write_output(results, settings.paths.output_csv)
    print(f"\nDone. Output written to {settings.paths.output_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
