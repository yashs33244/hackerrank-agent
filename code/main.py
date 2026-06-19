"""Entry point for the Multi-Modal Evidence Review system.

Examples:
    python code/main.py                 # full test set (dataset/claims.csv) -> output.csv
    python code/main.py --sample        # 20 labeled rows -> sample_output.csv
    python code/main.py --limit 3       # first 3 rows only (quick smoke run)

No API key is used: inference runs through the local ``claude`` CLI under the
user's Claude subscription (see AGENTS.md and code/agent/client.py).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make code/ the import root so bare package imports (config, pipeline, domain.*)
# resolve identically however this script is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from pipeline import run  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and run the pipeline over the chosen claims file."""
    parser = argparse.ArgumentParser(description="Multi-Modal Evidence Review")
    parser.add_argument("--claims", default=None, help="claims CSV (default dataset/claims.csv)")
    parser.add_argument("--output", default=None, help="output CSV (default output.csv)")
    parser.add_argument(
        "--sample", action="store_true", help="run the 20 labeled sample rows"
    )
    parser.add_argument("--limit", type=int, default=None, help="process only the first N rows")
    parser.add_argument("--workers", type=int, default=None, help="max concurrent workers")
    args = parser.parse_args(argv)

    if args.sample:
        claims = args.claims or str(config.SAMPLE_CLAIMS_CSV)
        output = args.output or str(config.REPO_ROOT / "sample_output.csv")
    else:
        claims = args.claims or str(config.CLAIMS_CSV)
        output = args.output or str(config.OUTPUT_CSV)

    print(f"Reading {claims}")
    started = time.time()
    rows = run(claims, output, config.DATASET_DIR, limit=args.limit, max_workers=args.workers)
    elapsed = time.time() - started
    print(f"Wrote {len(rows)} rows to {output} in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
