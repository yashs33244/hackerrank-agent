"""CLI entry point — three modes: single ticket, batch CSV, interactive REPL.

Usage (run from repo root):
    python code/cli.py --ticket "I can't log in" --company HackerRank
    python code/cli.py --ticket "..." --company "..." --subject "Login issue"
    python code/cli.py --csv support_tickets/support_tickets.csv
    python code/cli.py --interactive

Output for --ticket: JSON printed to stdout.
Output for --csv:    writes support_tickets/output.csv (same as main.py).
Output for --interactive: REPL prompting for ticket text, company, subject.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

# Allow running as `python code/cli.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings
from domain.types import TicketState
from pipeline import PipelineFactory


# ── Helpers ────────────────────────────────────────────────────────────────────

def _run_ticket(pipeline, ticket: str, company: str, subject: str) -> dict:
    state = TicketState(ticket=ticket, subject=subject, company=company)
    output = pipeline.run(state)
    return output.to_dict()


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = ["status", "product_area", "response", "justification", "request_type"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── Modes ──────────────────────────────────────────────────────────────────────

def cmd_single(args: argparse.Namespace) -> int:
    """Run a single ticket and print JSON to stdout."""
    print("Loading pipeline…", file=sys.stderr)
    pipeline = PipelineFactory.create()

    result = _run_ticket(
        pipeline,
        ticket=args.ticket,
        company=args.company or "",
        subject=args.subject or "",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_csv(args: argparse.Namespace) -> int:
    """Batch mode — process a CSV file and write output.csv."""
    input_path = Path(args.csv).resolve()
    if not input_path.exists():
        print(f"Error: CSV file not found: {input_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output).resolve() if args.output else settings.paths.output_csv

    print("Loading pipeline…", file=sys.stderr)
    pipeline = PipelineFactory.create()

    rows = _read_csv(input_path)
    total = len(rows)
    print(f"Processing {total} tickets from {input_path}…\n", file=sys.stderr)

    results: list[dict] = []
    for idx, row in enumerate(rows, start=1):
        ticket = (row.get("ticket") or row.get("Issue") or "").strip()
        subject = (row.get("subject") or row.get("Subject") or "").strip()
        company = (row.get("company") or row.get("Company") or "").strip()

        label = subject or ticket[:60]
        print(f"  [{idx:02d}/{total}] {label!r}", end="  ", flush=True, file=sys.stderr)

        try:
            result = _run_ticket(pipeline, ticket, company, subject)
            results.append(result)
            print(f"→ {result['status']}", file=sys.stderr)
        except Exception as exc:
            print(f"→ ERROR: {exc}", file=sys.stderr)
            results.append({
                "status": "escalated",
                "product_area": "error",
                "response": "An internal error occurred. Your ticket has been escalated.",
                "justification": f"Pipeline error: {exc}",
                "request_type": "product_issue",
            })

        if idx < total:
            time.sleep(1)

    _write_csv(results, output_path)
    print(f"\nDone. Output written to {output_path}", file=sys.stderr)
    return 0


def cmd_interactive(args: argparse.Namespace) -> int:
    """Interactive REPL — type a ticket, get a JSON response."""
    print("Loading pipeline…", file=sys.stderr)
    pipeline = PipelineFactory.create()

    print("\nSupport Triage Agent — Interactive Mode")
    print("Type 'exit' or press Ctrl-C to quit.\n")

    while True:
        try:
            ticket = input("Ticket text > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.", file=sys.stderr)
            return 0

        if ticket.lower() in {"exit", "quit", "q"}:
            return 0
        if not ticket:
            continue

        try:
            company = input("Company     > ").strip()
            subject = input("Subject     > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.", file=sys.stderr)
            return 0

        try:
            result = _run_ticket(pipeline, ticket, company, subject)
            print("\n" + json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        except Exception as exc:
            print(f"\nError: {exc}\n", file=sys.stderr)


# ── Argument parser ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="HackerRank Support Triage Agent — CLI interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python code/cli.py --ticket "Can't log in" --company HackerRank
  python code/cli.py --ticket "Billing question" --company Visa --subject "Charge dispute"
  python code/cli.py --csv support_tickets/support_tickets.csv
  python code/cli.py --csv support_tickets/support_tickets.csv --output /tmp/out.csv
  python code/cli.py --interactive
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--ticket", "-t",
        metavar="TEXT",
        help="Single ticket text; prints JSON to stdout.",
    )
    mode.add_argument(
        "--csv", "-f",
        metavar="FILE",
        help="Batch mode: process a CSV file.",
    )
    mode.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive REPL mode.",
    )

    parser.add_argument(
        "--company", "-c",
        metavar="NAME",
        default="",
        help="Company name (HackerRank | Claude | Visa). Used with --ticket.",
    )
    parser.add_argument(
        "--subject", "-s",
        metavar="TEXT",
        default="",
        help="Ticket subject line. Used with --ticket.",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        default="",
        help="Output CSV path. Used with --csv. Defaults to support_tickets/output.csv.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.ticket:
        return cmd_single(args)
    elif args.csv:
        return cmd_csv(args)
    elif args.interactive:
        return cmd_interactive(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
