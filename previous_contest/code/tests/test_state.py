"""TicketState behavior tests."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.types import TicketState  # noqa: E402
from domain.enums import Domain, RiskLevel  # noqa: E402


def test_initializes_from_ticket_row() -> None:
    state = TicketState(
        ticket="I lost access to my account",
        subject="Account access",
        company="Claude",
    )
    assert state.ticket == "I lost access to my account"
    assert state.company == "Claude"
    assert state.subject == "Account access"


def test_defaults_are_none_before_pipeline_runs() -> None:
    state = TicketState(ticket="test", subject="", company="None")
    assert state.domain is None
    assert state.intent is None
    assert state.risk_level is None
    assert state.retrieved_chunks == []
    assert state.draft_response is None
    assert state.critic_scores is None
    assert state.final_output is None


def test_status_defaults_to_none() -> None:
    state = TicketState(ticket="test", subject="", company="HackerRank")
    assert state.status is None


def test_is_mutable_for_pipeline_writes() -> None:
    state = TicketState(ticket="test", subject="", company="Visa")
    state.domain = Domain.VISA
    state.risk_level = RiskLevel.HIGH
    assert state.domain == Domain.VISA
    assert state.risk_level == RiskLevel.HIGH


def test_retry_count_starts_at_zero() -> None:
    state = TicketState(ticket="test", subject="", company="None")
    assert state.retry_count == 0
