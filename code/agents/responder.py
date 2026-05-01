"""ResponderAgent — corpus-grounded answer generation (Agentic RAG).

Cognitive load: MEDIUM (standard) / HIGH (risk_level=HIGH)
Reads:  ticket, intent, domain, status, risk_level, retry_count
Writes: search_result, draft_response

Calls search_corpus() as a tool (agent decides what to retrieve).
Hard cap: settings.pipeline.max_responder_calls per ticket.
"""
from __future__ import annotations

from agents.base import AbstractAgent
from config import settings
from domain.enums import RequestType, TicketStatus
from domain.types import ContextCompressor, LLMClient, Searcher, TicketState

_ESCALATED_RESPONSE = (
    "Thank you for reaching out. We understand this is important to you, and we want "
    "to make sure you get the right help. Your case has been forwarded to our support "
    "team, who will review it and follow up with you directly. If your situation is "
    "urgent, please don't hesitate to reach out through your account's support portal "
    "for faster assistance."
)

_OUT_OF_SCOPE_RESPONSE = (
    "Thanks for getting in touch. This particular request falls outside what our support "
    "system is able to assist with directly. If you have a question about HackerRank, "
    "Claude, or Visa services, please reach out through the relevant support channel "
    "and our team will be happy to help."
)


class ResponderAgent(AbstractAgent):
    """Generates corpus-grounded responses using agentic retrieval.

    Follows the Strategy pattern: the Searcher and ContextCompressor
    implementations are injected, not instantiated internally.
    """

    prompt_name = "responder"

    def __init__(
        self,
        client: LLMClient,
        high_client: LLMClient,
        searcher: Searcher,
        compressor: ContextCompressor,
    ) -> None:
        super().__init__(client)
        self._high_client = high_client
        self._searcher = searcher
        self._compressor = compressor

    def run(self, state: TicketState) -> TicketState:
        if state.status == TicketStatus.ESCALATED:
            state.draft_response = _ESCALATED_RESPONSE
            return state

        if state.request_type == RequestType.INVALID:
            state.draft_response = _OUT_OF_SCOPE_RESPONSE
            state.status = TicketStatus.REPLIED
            return state

        active_client = (
            self._high_client
            if state.risk_level and state.risk_level.value == "HIGH"
            else self._client
        )

        max_calls = settings.pipeline.max_responder_calls
        domain_str = state.domain.value if state.domain else None
        query = f"{state.intent or ''} {state.ticket}".strip()

        for attempt in range(max_calls):
            state.retry_count = attempt

            # Tool call: search_corpus (agentic RAG — agent decides query)
            chunks = self._searcher.search(
                query=query,
                top_k=settings.retrieval.final_top_k,
                domain=domain_str,
            )
            if not chunks and domain_str:
                # Fallback: search without domain filter
                chunks = self._searcher.search(
                    query=query,
                    top_k=settings.retrieval.final_top_k,
                    domain=None,
                )

            from domain.types import SearchResult
            state.search_result = SearchResult(
                chunks=chunks,
                query=query,
                domain_filter=domain_str,
                bm25_candidates=settings.retrieval.bm25_top_k,
                final_count=len(chunks),
            )

            corpus_context = self._compressor.compress(chunks, query)
            prompt = self._system_prompt.replace("{corpus_context}", corpus_context)

            user_msg = f"Support ticket:\n{state.ticket}\n\nUser intent: {state.intent}"
            if attempt > 0:
                user_msg += "\n\nNote: Previous response was insufficient. Provide a more complete, grounded answer."

            full_prompt = f"{prompt}\n\n{user_msg}"
            raw = active_client.generate_content(
                [{"role": "user", "parts": [full_prompt]}]
            )
            state.draft_response = self._extract_response_text(raw.text)

            if state.draft_response:
                break

        if not state.draft_response:
            state.draft_response = _ESCALATED_RESPONSE
            state.status = TicketStatus.ESCALATED

        return state
