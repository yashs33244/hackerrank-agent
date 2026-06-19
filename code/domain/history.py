"""User-history loader and the derived ``is_risky`` signal.

``user_history.csv`` carries one row per user with prior-claim counts and two
free-text fields: ``history_flags`` (a semicolon-joined set of risk tokens) and
``history_summary`` (a human note). ``is_risky`` is the single boolean the
decision tree consumes to add ``user_history_risk`` / ``manual_review_required``
color to a row.

WHY history is only a flag: per the locked decision rules (D11), user history
never flips ``claim_status`` - the pixels do. ``is_risky`` therefore only feeds
the risk-flag union, never the verdict. Risk is derived primarily from the
explicit ``history_flags`` tokens, with a conservative summary fallback so a
clearly-stated fraud/rejection note in a row whose flags read ``none`` is not
silently dropped.
"""

from __future__ import annotations

import csv
from pathlib import Path

from domain.types import UserHistory

# Tokens in ``history_flags`` that mark a user as risky. These are the exact
# flag strings the dataset uses; matching is case-insensitive and exact per
# split token (not substring) to avoid accidental hits.
_RISK_FLAG_TOKENS: frozenset[str] = frozenset(
    {"user_history_risk", "manual_review_required"}
)

# The literal a clean ``history_flags`` cell holds. Treated as "no flags".
_NO_FLAG_LITERAL = "none"

# Substrings in ``history_summary`` that independently signal risk even when the
# explicit flags are absent. Deliberately narrow: only unambiguous fraud /
# rejection language qualifies. WHY so narrow: ``history_flags`` is the
# authoritative risk signal (D11 - copy the flag, never invent), so the summary
# is only a safety net for clear fraud/rejection wording the flags somehow miss.
# Broad phrases like "manual review" are excluded because benign histories
# (e.g. "mostly accepted claims with one manual review") use them too, and
# treating those as risky would invent risk the flags do not assert.
_RISK_SUMMARY_PHRASES: tuple[str, ...] = (
    "fraud",
    "rejected mismatch",
    "prior rejection",
)

# Columns whose values are integer counts.
_INTEGER_COLUMNS: tuple[str, ...] = (
    "past_claim_count",
    "accept_claim",
    "manual_review_claim",
    "rejected_claim",
    "last_90_days_claim_count",
)

_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    ("user_id", "history_flags", "history_summary", *_INTEGER_COLUMNS)
)

# Multi-value cells are semicolon-joined, matching the output contract.
_FLAG_SEPARATOR = ";"


def load_history(path: str | Path) -> dict[str, UserHistory]:
    """Load every user-history row, keyed by ``user_id``.

    Args:
        path: Filesystem path to ``user_history.csv``.

    Returns:
        A mapping from ``user_id`` to its parsed ``UserHistory`` (with
        ``is_risky`` already derived).

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If a required column is missing or an integer cell is
            non-numeric.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"user history CSV not found: {csv_path}")

    history: dict[str, UserHistory] = {}
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _assert_columns(reader.fieldnames, _REQUIRED_COLUMNS, csv_path)
        for row in reader:
            record = _parse_row(row, csv_path)
            history[record.user_id] = record
    return history


def _parse_row(row: dict[str, str], csv_path: Path) -> UserHistory:
    """Build one ``UserHistory`` from a raw CSV row, deriving ``is_risky``."""
    user_id = row["user_id"].strip()
    flags = _parse_flags(row["history_flags"])
    summary = row["history_summary"].strip()
    return UserHistory(
        user_id=user_id,
        past_claim_count=_parse_int(row["past_claim_count"], "past_claim_count", csv_path),
        accept_claim=_parse_int(row["accept_claim"], "accept_claim", csv_path),
        manual_review_claim=_parse_int(
            row["manual_review_claim"], "manual_review_claim", csv_path
        ),
        rejected_claim=_parse_int(row["rejected_claim"], "rejected_claim", csv_path),
        last_90_days_claim_count=_parse_int(
            row["last_90_days_claim_count"], "last_90_days_claim_count", csv_path
        ),
        history_flags=flags,
        history_summary=summary,
        is_risky=_derive_is_risky(flags, summary),
    )


def _parse_flags(raw: str) -> list[str]:
    """Split the ``history_flags`` cell into individual tokens.

    The ``none`` literal collapses to an empty list so callers can treat a clean
    user as "no flags" without a special case.
    """
    tokens = [token.strip() for token in raw.split(_FLAG_SEPARATOR)]
    return [
        token
        for token in tokens
        if token and token.lower() != _NO_FLAG_LITERAL
    ]


def _derive_is_risky(flags: list[str], summary: str) -> bool:
    """True when explicit flags or the summary indicate elevated risk."""
    if any(flag.lower() in _RISK_FLAG_TOKENS for flag in flags):
        return True
    summary_lower = summary.lower()
    return any(phrase in summary_lower for phrase in _RISK_SUMMARY_PHRASES)


def _parse_int(raw: str, column: str, csv_path: Path) -> int:
    """Parse an integer count, raising a clear error on bad data."""
    text = (raw or "").strip()
    try:
        return int(text)
    except ValueError as error:
        raise ValueError(
            f"{csv_path}: column '{column}' has non-integer value {raw!r}"
        ) from error


def _assert_columns(
    fieldnames: list[str] | None,
    required: frozenset[str],
    csv_path: Path,
) -> None:
    """Fail loudly if the CSV header is missing a column we depend on."""
    present = set(fieldnames or ())
    missing = required - present
    if missing:
        raise ValueError(
            f"{csv_path} is missing required column(s): {sorted(missing)}"
        )
