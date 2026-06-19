"""BM25Searcher — hybrid keyword + cosine-similarity retrieval.

Retrieval stack (AD-3):
  1. BM25 keyword filter — eliminates ~95% of irrelevant chunks, zero LLM cost
  2. Cosine similarity rerank over BM25 survivors (when embeddings available)
  3. Contextual headers on every chunk for CriticAgent traceability

Implements the Searcher Protocol defined in domain.types.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

import numpy as np
from rank_bm25 import BM25Okapi

from config import settings
from domain.types import Chunk


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


class BM25Searcher:
    """Loads a pre-built index and answers search queries.

    Implements the Searcher Protocol — can be swapped for any alternative
    retrieval backend (e.g., vector DB, Elasticsearch) without changing agents.
    """

    def __init__(self, index_dir: Optional[Path] = None) -> None:
        self._index_dir = index_dir or settings.paths.index_dir
        self._chunks: List[Chunk] = self._load_chunks()
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in self._chunks])
        self._embeddings: Optional[np.ndarray] = self._load_embeddings()

    def _load_chunks(self) -> List[Chunk]:
        chunks_path = self._index_dir / "chunks.jsonl"
        chunks: List[Chunk] = []
        with chunks_path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    chunks.append(Chunk(**json.loads(line)))
        return chunks

    def _load_embeddings(self) -> Optional[np.ndarray]:
        path = self._index_dir / "embeddings.npy"
        if path.exists():
            return np.load(path)
        return None

    def search(
        self,
        query: str,
        top_k: int = 3,
        domain: Optional[str] = None,
        query_embedding: Optional[np.ndarray] = None,
    ) -> List[Chunk]:
        """Return the top-k most relevant Chunk objects for the query."""
        if not query.strip():
            return []

        # Stage 1: domain-scoped candidate set
        candidates = self._chunks
        if domain and domain != "unknown":
            filtered = [c for c in candidates if c.domain == domain.lower()]
            candidates = filtered if filtered else candidates  # never return 0

        # Stage 2: BM25 ranking over candidate set
        candidate_ids = [c.id for c in candidates]
        all_scores = self._bm25.get_scores(_tokenize(query))
        scored: List[tuple[float, int]] = [
            (all_scores[cid], cid) for cid in candidate_ids
        ]
        scored.sort(reverse=True)

        # Stage 3: cosine rerank when a query embedding is available
        bm25_pool = int(settings.retrieval.bm25_top_k)
        if query_embedding is not None and self._embeddings is not None:
            top_ids = [cid for _, cid in scored[:bm25_pool]]
            top_embs = self._embeddings[top_ids]
            q = query_embedding / (np.linalg.norm(query_embedding) + 1e-9)
            normed = top_embs / (np.linalg.norm(top_embs, axis=1, keepdims=True) + 1e-9)
            cos = normed @ q
            reranked = sorted(zip(cos, top_ids), reverse=True)
            final_ids = [cid for _, cid in reranked[:top_k]]
        else:
            final_ids = [cid for _, cid in scored[:top_k]]

        id_to_chunk = {c.id: c for c in self._chunks}
        return [id_to_chunk[cid] for cid in final_ids if cid in id_to_chunk]
