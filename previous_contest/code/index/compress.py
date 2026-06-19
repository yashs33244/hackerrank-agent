"""ContextCompressor — LLM-driven extractive compression.

Implements the ContextCompressor Protocol defined in domain.types.
Reduces retrieved-chunk token count by ~60-80% before passing to the
ResponderAgent, keeping the Responder's context window focused.

Uses a low-load model (Flash-Lite) for efficiency.
"""
from __future__ import annotations

from typing import List

from domain.types import Chunk, ContextCompressor, LLMClient

_COMPRESSION_PROMPT = """\
You are a context compression assistant. Your job is to extract only the
sentences that are directly relevant to answering the user's query. Preserve
source headers exactly. Output ONLY the compressed text — no introduction,
no explanation.

Query: {query}

Retrieved excerpts:
{raw}

Compressed relevant context (keep source headers):"""


class LLMContextCompressor:
    """Compresses retrieved chunks to only query-relevant sentences.

    Implements the ContextCompressor Protocol.
    """

    _MAX_CHARS_PER_CHUNK = 2000

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def compress(self, chunks: List[Chunk], query: str) -> str:
        if not chunks:
            return "(no corpus context retrieved)"

        raw_parts = [
            c.full_text[: self._MAX_CHARS_PER_CHUNK] for c in chunks
        ]
        raw = "\n---\n".join(raw_parts)

        prompt = _COMPRESSION_PROMPT.format(query=query, raw=raw)
        response = self._client.generate_content(
            [{"role": "user", "parts": [prompt]}]
        )
        return response.text.strip() or raw
