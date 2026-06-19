"""AbstractAgent — base class for all pipeline agents.

Enforces:
  - Single Responsibility: each subclass handles exactly one pipeline stage
  - Open/Closed: extend by subclassing, not by modifying this class
  - Liskov Substitution: all agents are interchangeable via the abstract interface
  - Dependency Inversion: agents depend on the LLMClient protocol, not on Gemini directly
"""
from __future__ import annotations

import abc
import json
import re
from pathlib import Path
from typing import Any

from config import settings
from domain.types import LLMClient, TicketState


class AbstractAgent(abc.ABC):
    """Base class for all single-responsibility pipeline agents."""

    # Subclasses declare their prompt filename (without extension)
    prompt_name: str = ""

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self._system_prompt: str = self._load_prompt()

    def _load_prompt(self) -> str:
        if not self.prompt_name:
            return ""
        path = settings.paths.prompts_dir / f"{self.prompt_name}.md"
        return path.read_text(encoding="utf-8")

    @abc.abstractmethod
    def run(self, state: TicketState) -> TicketState:
        """Process state. Read only relevant fields. Write only owned fields."""
        ...

    def _call_llm(self, user_message: str) -> str:
        """Call the LLM with the agent's system prompt + user message."""
        full_prompt = f"{self._system_prompt}\n\n{user_message}"
        response = self._client.generate_content(
            [{"role": "user", "parts": [full_prompt]}]
        )
        return response.text

    def _parse_json(self, text: str) -> dict:
        """Extract the first JSON object from model output."""
        # Strip thinking blocks
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
        # Strip markdown fences
        text = re.sub(r"```(?:json)?", "", text)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    def _extract_response_text(self, text: str) -> str:
        """Return text after </thinking> tags for Responder responses."""
        match = re.search(r"</thinking>(.*)", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # No thinking tags — strip any stray JSON and return
        cleaned = re.sub(r"\{[^{}]*\}", "", text, flags=re.DOTALL).strip()
        return cleaned or text.strip()
