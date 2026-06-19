"""Tests for the user-history loader and the derived ``is_risky`` flag.

Loads the real ``dataset/user_history.csv`` (47 users) so the asserted
risk classification is grounded in the actual data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from domain.history import load_history  # noqa: E402
from domain.types import UserHistory  # noqa: E402

HISTORY_CSV = REPO_ROOT / "dataset" / "user_history.csv"


@pytest.fixture(scope="module")
def history() -> dict[str, UserHistory]:
    return load_history(HISTORY_CSV)


def test_load_history_returns_all_users(history: dict[str, UserHistory]) -> None:
    assert len(history) == 47
    assert "user_001" in history
    assert "user_047" in history


def test_load_history_parses_numeric_columns(
    history: dict[str, UserHistory],
) -> None:
    record = history["user_002"]
    assert isinstance(record, UserHistory)
    assert record.past_claim_count == 4
    assert record.accept_claim == 3
    assert record.manual_review_claim == 1
    assert record.rejected_claim == 0
    assert record.last_90_days_claim_count == 2


def test_clean_user_is_not_risky(history: dict[str, UserHistory]) -> None:
    # user_001: history_flags == "none", benign summary.
    record = history["user_001"]
    assert record.is_risky is False
    assert record.history_flags == []


def test_user_history_risk_flag_is_risky(history: dict[str, UserHistory]) -> None:
    # user_005: history_flags == "user_history_risk".
    record = history["user_005"]
    assert record.is_risky is True
    assert "user_history_risk" in record.history_flags


def test_manual_review_only_flag_is_risky(history: dict[str, UserHistory]) -> None:
    # user_032: history_flags == "manual_review_required" (no user_history_risk).
    record = history["user_032"]
    assert record.is_risky is True
    assert "manual_review_required" in record.history_flags


def test_multi_flag_user_is_risky(history: dict[str, UserHistory]) -> None:
    # user_013: history_flags == "user_history_risk;manual_review_required".
    record = history["user_013"]
    assert record.is_risky is True
    assert set(record.history_flags) == {
        "user_history_risk",
        "manual_review_required",
    }


def test_new_user_with_no_history_is_not_risky(
    history: dict[str, UserHistory],
) -> None:
    # user_006: brand-new user, flags "none".
    record = history["user_006"]
    assert record.is_risky is False
    assert record.past_claim_count == 0
    assert record.history_summary  # summary text preserved


def test_summary_heuristic_marks_rejection(tmp_path: Path) -> None:
    csv_path = tmp_path / "tiny_history.csv"
    csv_path.write_text(
        '"user_id","past_claim_count","accept_claim","manual_review_claim",'
        '"rejected_claim","last_90_days_claim_count","history_flags",'
        '"history_summary"\n'
        '"user_999","3","1","0","0","1","none",'
        '"Prior claim was a likely fraud risk and prior rejection"\n',
        encoding="utf-8",
    )
    history = load_history(csv_path)
    record = history["user_999"]
    assert record.is_risky is True


def test_load_history_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_history(tmp_path / "absent.csv")
