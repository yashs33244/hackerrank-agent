"""CriticAgent — Gate 2: post-draft quality check.

Cognitive load: LOW
Reads:  ticket, draft_response, retrieved_chunks, status
Writes: critic_scores

Scoring dimensions: grounding (0-10), safety (0-10), completeness (0-10)
A response must meet settings.pipeline.critic_pass_threshold on all three.
Safety < threshold → forced escalation regardless of other scores.
"""
from __future__ import annotations

from agents.base import AbstractAgent
from config import settings
from domain.enums import TicketStatus
from domain.types import CriticScores, LLMClient, TicketState


class CriticAgent(AbstractAgent):
    """Evaluates response quality and enforces grounding/safety guarantees."""

    prompt_name = "critic"

    def __init__(self, client: LLMClient) -> None:
        super().__init__(client)

    def run(self, state: TicketState) -> TicketState:
        # Critic only runs when there is a draft and the ticket is not yet
        # force-escalated by the router (pre-flight gate).
        if not state.draft_response:
            return state
        if state.status == TicketStatus.ESCALATED and not state.retrieved_chunks:
            return state

        corpus_excerpts = "\n---\n".join(
            c.full_text for c in state.retrieved_chunks[:5]
        )
        user_msg = (
            f"Original ticket:\n{state.ticket}\n\n"
            f"Draft response:\n{state.draft_response}\n\n"
            f"Corpus excerpts:\n{corpus_excerpts}"
        )

        raw = self._call_llm(user_msg)
        data = self._parse_json(raw)

        threshold = settings.pipeline.critic_pass_threshold

        grounding = int(data.get("grounding", 0))
        safety = int(data.get("safety", 0))
        completeness = int(data.get("completeness", 0))
        passed = (
            grounding >= threshold
            and safety >= threshold
            and completeness >= threshold
        )

        state.critic_scores = CriticScores(
            grounding=grounding,
            safety=safety,
            completeness=completeness,
            passed=passed,
            critique=data.get("critique", ""),
        )

        # Safety is a hard gate — force escalation if the response is unsafe
        if safety < threshold:
            state.status = TicketStatus.ESCALATED
            if state.triage_reason:
                state.triage_reason += f" | Critic forced escalation: safety={safety}"
            else:
                state.triage_reason = f"Critic forced escalation: safety={safety}"

        return state
