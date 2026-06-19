"""Pipeline — orchestrates the five-agent chain per ticket.

Flow:
  RouterAgent → TriageAgent → ResponderAgent ↔ CriticAgent (loop) → FormatterAgent

Design decisions:
  - RouterAgent: pre-flight safety screen (token-free) + domain classification
  - TriageAgent: escalate vs reply (may be skipped if pre-flight already decided)
  - Responder ↔ Critic loop: up to settings.pipeline.max_responder_calls
  - FormatterAgent: deterministic CSV column derivation, no LLM

The Pipeline itself is a pure orchestrator — it does not contain any
business logic. Each agent is injected, satisfying the Dependency Inversion
principle.
"""
from __future__ import annotations

from agents.critic import CriticAgent
from agents.formatter import FormatterAgent
from agents.responder import ResponderAgent
from agents.router import RouterAgent
from agents.triage import TriageAgent
from config import settings
from domain.enums import TicketStatus
from domain.types import TicketOutput, TicketState


class Pipeline:
    """Orchestrates agent execution in the correct order."""

    def __init__(
        self,
        router: RouterAgent,
        triage: TriageAgent,
        responder: ResponderAgent,
        critic: CriticAgent,
        formatter: FormatterAgent,
    ) -> None:
        self._router = router
        self._triage = triage
        self._responder = responder
        self._critic = critic
        self._formatter = formatter

    def run(self, state: TicketState) -> TicketOutput:
        # Stage 1: classify + pre-flight gate
        state = self._router.run(state)

        # Stage 2: triage (skipped if router already set status)
        state = self._triage.run(state)

        # Stage 3: respond + critic feedback loop
        max_calls = settings.pipeline.max_responder_calls
        threshold = settings.pipeline.critic_pass_threshold

        for _ in range(max_calls):
            state = self._responder.run(state)
            state = self._critic.run(state)

            # Stop looping when critic passes, ticket is escalated, or no draft
            if state.status == TicketStatus.ESCALATED:
                break
            if state.critic_scores and state.critic_scores.all_pass(threshold):
                break

        # Stage 4: deterministic column formatting
        state = self._formatter.run(state)

        return state.final_output  # type: ignore[return-value]


class PipelineFactory:
    """Constructs a Pipeline with all dependencies wired.

    Single point of composition — changes to dependencies happen here only.
    """

    @staticmethod
    def create() -> Pipeline:
        from agents.gemini_client import GeminiClientFactory
        from index.compress import LLMContextCompressor
        from index.search import BM25Searcher

        factory = GeminiClientFactory()
        low = factory.low()
        medium = factory.medium()
        high = factory.high()

        searcher = BM25Searcher()
        compressor = LLMContextCompressor(low)

        return Pipeline(
            router=RouterAgent(client=low),
            triage=TriageAgent(client=medium),
            responder=ResponderAgent(
                client=medium,
                high_client=high,
                searcher=searcher,
                compressor=compressor,
            ),
            critic=CriticAgent(client=low),
            formatter=FormatterAgent(),
        )

    @staticmethod
    def create_with_config(
        provider: str,
        api_key: str,
        low_model: str,
        medium_model: str,
        high_model: str,
    ) -> Pipeline:
        """Construct a Pipeline from explicit provider/key/model config.

        Used by the CLI wizard so the user's runtime choices take effect
        without relying on .env for the primary key.
        """
        from index.compress import LLMContextCompressor
        from index.search import BM25Searcher

        provider = provider.lower()

        if provider == "gemini":
            from agents.gemini_client import GeminiClient
            from google import genai as _genai
            sdk = _genai.Client(api_key=api_key)
            low = GeminiClient(low_model, sdk)
            medium = GeminiClient(medium_model, sdk)
            high = GeminiClient(high_model, sdk)
        elif provider == "anthropic":
            from agents.anthropic_client import AnthropicClient
            low = AnthropicClient(low_model, api_key)
            medium = AnthropicClient(medium_model, api_key)
            high = AnthropicClient(high_model, api_key)
        elif provider == "openai":
            from agents.openai_client import OpenAIClient
            low = OpenAIClient(low_model, api_key)
            medium = OpenAIClient(medium_model, api_key)
            high = OpenAIClient(high_model, api_key)
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Choose gemini, anthropic, or openai.")

        searcher = BM25Searcher()
        compressor = LLMContextCompressor(low)

        return Pipeline(
            router=RouterAgent(client=low),
            triage=TriageAgent(client=medium),
            responder=ResponderAgent(
                client=medium,
                high_client=high,
                searcher=searcher,
                compressor=compressor,
            ),
            critic=CriticAgent(client=low),
            formatter=FormatterAgent(),
        )
