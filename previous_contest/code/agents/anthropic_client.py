"""AnthropicClient — LLMClient implementation backed by Anthropic Claude."""
from __future__ import annotations

import time
from typing import Optional


class _ApiResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str:
        return self._text


class AnthropicClient:
    """LLMClient implementation for Anthropic Claude models."""

    _MAX_RETRIES = 4
    _BASE_BACKOFF_SECS = 5

    def __init__(self, model_name: str, api_key: str) -> None:
        self._model = model_name
        self._api_key = api_key
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def generate_content(self, messages: list) -> _ApiResponse:
        prompt = messages[0]["parts"][0] if messages else ""
        last_exc: Optional[Exception] = None

        for attempt in range(self._MAX_RETRIES):
            try:
                client = self._get_client()
                response = client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text if response.content else ""
                return _ApiResponse(text)
            except Exception as exc:
                last_exc = exc
                if "429" in str(exc) or "rate_limit" in str(exc).lower() or "overloaded" in str(exc).lower():
                    wait = self._BASE_BACKOFF_SECS * (2 ** attempt)
                    time.sleep(wait)
                else:
                    raise

        raise last_exc  # type: ignore[misc]


class AnthropicClientFactory:
    """Factory producing AnthropicClient instances by cognitive load."""

    def __init__(self, api_key: str, low_model: str, medium_model: str, high_model: str) -> None:
        self._api_key = api_key
        self._low_model = low_model
        self._medium_model = medium_model
        self._high_model = high_model

    def low(self) -> AnthropicClient:
        return AnthropicClient(self._low_model, self._api_key)

    def medium(self) -> AnthropicClient:
        return AnthropicClient(self._medium_model, self._api_key)

    def high(self) -> AnthropicClient:
        return AnthropicClient(self._high_model, self._api_key)
