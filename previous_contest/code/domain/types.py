"""Domain types — all dataclasses, TypedDicts, and Protocols.

All public interfaces are defined here. Implementation files import from
this module, never from each other's implementation modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from domain.enums import (
    CognitiveLoad,
    Domain,
    RequestType,
    RiskLevel,
    TicketStatus,
)


# ── Retrieval ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Chunk:
    """An immutable corpus chunk with source metadata."""
    id: int
    source_path: str
    domain: str
    header: str
    text: str

    @property
    def full_text(self) -> str:
        return f"[Source: {self.header}]\n{self.text}"


@dataclass
class SearchResult:
    """Result from a search_corpus() tool call."""
    chunks: List[Chunk]
    query: str
    domain_filter: Optional[str]
    bm25_candidates: int
    final_count: int


# ── Critic ────────────────────────────────────────────────────────────────────

@dataclass
class CriticScores:
    grounding: int
    safety: int
    completeness: int
    passed: bool
    critique: str

    def all_pass(self, threshold: int) -> bool:
        return (
            self.grounding >= threshold
            and self.safety >= threshold
            and self.completeness >= threshold
        )


# ── Pipeline state ────────────────────────────────────────────────────────────

@dataclass
class TicketState:
    """Single typed object flowing through the entire pipeline.

    Each agent reads only its relevant fields and writes only its output
    fields. Context windows stay scoped — no agent reads another agent's
    full reasoning trace.
    """
    # ── Input (immutable after init) ───────────────────────────────────────
    ticket: str
    subject: str
    company: str

    # ── RouterAgent writes ─────────────────────────────────────────────────
    domain: Optional[Domain] = None
    intent: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    request_type: Optional[RequestType] = None
    product_area: Optional[str] = None  # canonical area name from router

    # ── TriageAgent writes ─────────────────────────────────────────────────
    status: Optional[TicketStatus] = None
    triage_reason: Optional[str] = None

    # ── ResponderAgent writes ──────────────────────────────────────────────
    search_result: Optional[SearchResult] = None
    draft_response: Optional[str] = None
    retry_count: int = 0

    # ── CriticAgent writes ─────────────────────────────────────────────────
    critic_scores: Optional[CriticScores] = None

    # ── FormatterAgent writes ──────────────────────────────────────────────
    final_output: Optional["TicketOutput"] = None

    @property
    def retrieved_chunks(self) -> List[Chunk]:
        return self.search_result.chunks if self.search_result else []


@dataclass
class TicketOutput:
    """The 5 required output columns — one per ticket row."""
    status: str
    product_area: str
    response: str
    justification: str
    request_type: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "product_area": self.product_area,
            "response": self.response,
            "justification": self.justification,
            "request_type": self.request_type,
        }


# ── Protocols (dependency injection contracts) ─────────────────────────────────

class LLMClient(Protocol):
    """Contract that all LLM client wrappers must satisfy."""
    def generate_content(self, messages: list) -> object:
        ...


class Searcher(Protocol):
    """Contract for retrieval implementations."""
    def search(
        self,
        query: str,
        top_k: int,
        domain: Optional[str],
    ) -> List[Chunk]:
        ...


class ContextCompressor(Protocol):
    """Contract for context compression implementations."""
    def compress(self, chunks: List[Chunk], query: str) -> str:
        ...
