"""GeminiClient — factory and wrapper for the google-genai SDK.

Responsibilities:
  - Singleton client management
  - Model-tier routing (LOW / MEDIUM / HIGH)
  - Exponential backoff retry on 429 RESOURCE_EXHAUSTED
  - Presents the LLMClient protocol to the rest of the system

Nothing outside this module should import google.genai directly.
"""
from __future__ import annotations

import time
from typing import Optional

from google import genai

from config import settings
from domain.enums import CognitiveLoad


class _ApiResponse:
    """Thin wrapper normalising the genai response object."""

    def __init__(self, raw: object) -> None:
        self._raw = raw

    @property
    def text(self) -> str:
        return getattr(self._raw, "text", "") or ""


class GeminiClient:
    """LLMClient implementation backed by Google Gemini.

    One instance per cognitive-load tier. Constructed by GeminiClientFactory.
    """

    _MAX_RETRIES = 4
    _BASE_BACKOFF_SECS = 5

    def __init__(self, model_name: str, sdk_client: genai.Client) -> None:
        self._model = model_name
        self._sdk = sdk_client

    def generate_content(self, messages: list) -> _ApiResponse:
        prompt = messages[0]["parts"][0] if messages else ""
        last_exc: Optional[Exception] = None

        for attempt in range(self._MAX_RETRIES):
            try:
                raw = self._sdk.models.generate_content(
                    model=self._model,
                    contents=prompt,
                )
                return _ApiResponse(raw)
            except Exception as exc:
                last_exc = exc
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                    wait = self._BASE_BACKOFF_SECS * (2 ** attempt)
                    print(
                        f"\n         [rate limit] waiting {wait}s "
                        f"(attempt {attempt + 1}/{self._MAX_RETRIES})...",
                        end="",
                        flush=True,
                    )
                    time.sleep(wait)
                else:
                    raise

        raise last_exc  # type: ignore[misc]


class GeminiClientFactory:
    """Factory — produces GeminiClient instances keyed by cognitive load.

    Clients are cached after first creation (flyweight pattern).
    """

    def __init__(self) -> None:
        self._sdk = genai.Client(api_key=settings.api_key)
        self._cache: dict[CognitiveLoad, GeminiClient] = {}

    def get(self, load: CognitiveLoad) -> GeminiClient:
        if load not in self._cache:
            model_name = {
                CognitiveLoad.LOW: settings.models.low,
                CognitiveLoad.MEDIUM: settings.models.medium,
                CognitiveLoad.HIGH: settings.models.high,
            }[load]
            self._cache[load] = GeminiClient(model_name, self._sdk)
        return self._cache[load]

    def low(self) -> GeminiClient:
        return self.get(CognitiveLoad.LOW)

    def medium(self) -> GeminiClient:
        return self.get(CognitiveLoad.MEDIUM)

    def high(self) -> GeminiClient:
        return self.get(CognitiveLoad.HIGH)
