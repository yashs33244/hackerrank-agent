"""TriageAgent — escalate vs reply decision.

Cognitive load: MEDIUM
Reads:  ticket, intent, risk_level, request_type, domain
Writes: status, triage_reason

Skips entirely if RouterAgent already set status (pre-flight escalation).
"""
from __future__ import annotations

from agents.base import AbstractAgent
from domain.enums import RequestType, RiskLevel, TicketStatus
from domain.types import LLMClient, TicketState


class TriageAgent(AbstractAgent):
    """Makes the single escalate/reply decision with explicit reasoning."""

    prompt_name = "triage"

    def __init__(self, client: LLMClient) -> None:
        super().__init__(client)

    def run(self, state: TicketState) -> TicketState:
        # Pre-flight escalations are final — skip triage
        if state.status is not None:
            return state

        user_msg = (
            f"Ticket: {state.ticket}\n\n"
            f"Router classification:\n"
            f"  domain: {state.domain}\n"
            f"  intent: {state.intent}\n"
            f"  risk_level: {state.risk_level}\n"
            f"  request_type: {state.request_type}"
        )

        raw = self._call_llm(user_msg)
        data = self._parse_json(raw)

        status_raw = data.get("status", "escalated")
        try:
            state.status = TicketStatus(status_raw)
        except ValueError:
            state.status = TicketStatus.ESCALATED

        state.triage_reason = data.get("triage_reason", "")

        # Hard safety gate: only CRITICAL (pre-flight caught) is auto-escalated.
        # HIGH risk goes through triage reasoning — the triage prompt decides.
        # CRITICAL is already handled by RouterAgent pre-flight, so this is a
        # belt-and-suspenders check.
        if state.risk_level == RiskLevel.CRITICAL:
            state.status = TicketStatus.ESCALATED
            state.triage_reason = (
                state.triage_reason
                or f"Auto-escalated: risk_level=CRITICAL"
            )

        return state
