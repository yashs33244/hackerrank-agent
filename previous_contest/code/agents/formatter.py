"""FormatterAgent — produces the 5 CSV output columns. No LLM calls.

Cognitive load: NONE (pure deterministic logic)
Reads:  status, product_area (from router), domain, retrieved_chunks,
        draft_response, critic_scores, triage_reason, request_type
Writes: final_output (TicketOutput)

product_area priority:
  1. state.product_area (set by RouterAgent from LLM classification)
  2. header-based extraction from retrieved chunks (fallback)
  3. domain name (last resort)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from domain.enums import RequestType, TicketStatus
from domain.types import LLMClient, TicketOutput, TicketState

_FALLBACK_AREA = "general"

# Level-2 header section → canonical GT area name
_SECTION_AREA_MAP: Dict[str, str] = {
    # HackerRank
    "screen": "screen",
    "hackerrank community": "community",
    "integrations": "integrations",
    "interviews": "interviews",
    "engage": "engage",
    "skillup": "skillup",
    "settings": "settings",
    "library": "library",
    "general help": "general_help",
    "chakra": "chakra",
    "uncategorized": "general",
    # Claude
    "privacy and legal": "privacy",
    "claude": "conversation_management",   # claude/claude/ product section
    "conversation management": "conversation_management",
    "account management": "account_management",
    "safeguards": "safeguards",
    "pro and max plans": "plans",
    "claude api and console": "api_console",
    "amazon bedrock": "amazon_bedrock",
    "team and enterprise plans": "enterprise",
    "claude for education": "education",
    "claude desktop": "desktop",
    "claude mobile apps": "mobile",
    "claude code": "code",
    "identity management sso jit scim": "identity_management",
    "connectors": "connectors",
    "claude in chrome": "chrome",
    # Visa
    "travel support": "travel_support",
    "consumer": "general_support",
    "support": "general_support",
    "small business": "small_business",
}


class FormatterAgent:
    """Produces the 5 required CSV columns deterministically."""

    prompt_name = ""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self._client = client
        self._system_prompt = ""

    def run(self, state: TicketState) -> TicketState:
        status = (state.status or TicketStatus.ESCALATED).value
        product_area = self._resolve_product_area(state)
        response = state.draft_response or ""
        justification = self._build_justification(state)
        request_type = (state.request_type.value if state.request_type else "product_issue")

        state.final_output = TicketOutput(
            status=status,
            product_area=product_area,
            response=response,
            justification=justification,
            request_type=request_type,
        )
        return state

    # ── Area resolution ───────────────────────────────────────────────────────

    def _resolve_product_area(self, state: TicketState) -> str:
        """Priority chain for product_area resolution."""

        # 1. Escalated tickets always have empty area
        if state.status == TicketStatus.ESCALATED:
            return ""

        # 2. Use router-classified product_area if explicitly set (even if empty string)
        if state.product_area is not None:
            return state.product_area

        # 3. Fall back to header-based extraction from retrieved chunks
        for chunk in state.retrieved_chunks:
            area = self._extract_area_from_header(chunk.header)
            if area:
                return area

        # 4. Use domain as last resort
        if state.domain:
            return state.domain.value

        return _FALLBACK_AREA

    @staticmethod
    def _extract_area_from_header(header: str) -> str:
        """Extract canonical area name from chunk header.

        Header format: domain > section1 > [section2] > ... > filename
        Strategy: iterate sections from most specific (last) to least, return
        first match in _SECTION_AREA_MAP.
        """
        parts = [p.strip() for p in header.split(">")]
        # Remove domain (first) and filename (last)
        sections = parts[1:-1]

        # Iterate from most specific to least specific section
        for section in reversed(sections):
            key = section.lower().replace("-", " ").replace("_", " ")
            if key in _SECTION_AREA_MAP:
                return _SECTION_AREA_MAP[key]

        return ""

    # ── Justification builder ─────────────────────────────────────────────────

    @staticmethod
    def _build_justification(state: TicketState) -> str:
        parts: List[str] = []

        if state.triage_reason:
            parts.append(state.triage_reason)

        if state.critic_scores:
            c = state.critic_scores
            scores = (
                f"grounding={c.grounding}/10, "
                f"safety={c.safety}/10, "
                f"completeness={c.completeness}/10"
            )
            parts.append(f"Critic scores: {scores}")
            if c.critique:
                parts.append(c.critique)

        sources: List[str] = []
        for chunk in state.retrieved_chunks[:3]:
            area = FormatterAgent._extract_area_from_header(chunk.header) or chunk.source_path
            if area not in sources:
                sources.append(area)
        if sources:
            parts.append(f"Sources: {', '.join(sources)}")

        return " | ".join(parts) if parts else "Auto-classified"
