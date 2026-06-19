"""Backwards-compatibility shim — logic moved to gemini_client.py and base.py."""
from agents.gemini_client import GeminiClient, GeminiClientFactory  # noqa: F401
from agents.base import AbstractAgent  # noqa: F401
