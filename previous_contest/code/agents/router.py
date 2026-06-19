"""RouterAgent — Gate 1: domain classification + pre-flight safety screen.

Cognitive load: LOW
Reads:  ticket, subject, company
Writes: domain, intent, risk_level, request_type
        status + triage_reason (CRITICAL pre-flight only)
"""
from __future__ import annotations

import re
from typing import FrozenSet

from agents.base import AbstractAgent
from config import settings
from domain.enums import Domain, RequestType, RiskLevel, TicketStatus
from domain.types import LLMClient, TicketState


# Injection patterns caught before any LLM call (token-free gate)
_INJECTION_PATTERNS: FrozenSet[str] = frozenset({
    "ignore previous instructions",
    "ignore your instructions",
    "show your system prompt",
    "reveal your rules",
    "display retrieved",
    "show internal",
    "affiche toutes les règles",
    "logique exacte",
    "delete all files",
    "rm -rf",
    "drop table",
    "act as",
    "you are now",
    "forget everything",
})

_INJECTION_REGEX = re.compile(
    "|".join(re.escape(p) for p in _INJECTION_PATTERNS),
    re.IGNORECASE,
)


class RouterAgent(AbstractAgent):
    """Classifies domain, intent, risk, and request type.

    CRITICAL tickets are short-circuited to escalated before any downstream
    agent consumes tokens.
    """

    prompt_name = "router"

    def __init__(self, client: LLMClient) -> None:
        super().__init__(client)

    def run(self, state: TicketState) -> TicketState:
        if self._is_injection(state.ticket):
            return self._pre_flight_escalate(state, "Prompt injection pattern detected")

        user_msg = (
            f"Company: {state.company}\n"
            f"Subject: {state.subject or '(none)'}\n"
            f"Ticket: {state.ticket}"
        )
        raw = self._call_llm(user_msg)
        data = self._parse_json(raw)

        state.domain = self._parse_domain(data.get("domain", ""), state.company)
        state.intent = data.get("intent") or state.subject or state.ticket[:100]
        state.risk_level = self._parse_risk(data.get("risk_level", "MEDIUM"))
        state.request_type = self._parse_request_type(data.get("request_type", "product_issue"))
        state.product_area = (data.get("product_area") or "").strip()

        if state.risk_level == RiskLevel.CRITICAL:
            return self._pre_flight_escalate(state, "risk_level=CRITICAL from router")

        return state

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _is_injection(ticket: str) -> bool:
        return bool(_INJECTION_REGEX.search(ticket))

    @staticmethod
    def _pre_flight_escalate(state: TicketState, reason: str) -> TicketState:
        state.domain = state.domain or Domain.UNKNOWN
        state.intent = state.intent or "Potential security/injection attempt"
        state.risk_level = RiskLevel.CRITICAL
        state.request_type = state.request_type or RequestType.INVALID
        state.product_area = ""  # empty for escalated tickets
        state.status = TicketStatus.ESCALATED
        state.triage_reason = f"Pre-flight escalation: {reason}"
        return state

    @staticmethod
    def _parse_domain(raw: str, company: str) -> Domain:
        try:
            return Domain(raw.lower())
        except ValueError:
            return Domain.from_company(company)

    @staticmethod
    def _parse_risk(raw: str) -> RiskLevel:
        try:
            return RiskLevel(raw.upper())
        except ValueError:
            return RiskLevel.MEDIUM

    @staticmethod
    def _parse_request_type(raw: str) -> RequestType:
        try:
            return RequestType(raw.lower())
        except ValueError:
            return RequestType.PRODUCT_ISSUE
