"""BM25Searcher behavior tests — no LLM, no API calls."""
from __future__ import annotations

import json
import pathlib
import sys
import os

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from index.search import BM25Searcher  # noqa: E402
from domain.types import Chunk  # noqa: E402


def _make_fake_index(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write minimal fake chunks.jsonl + embeddings.npy for tests."""
    chunks = [
        {
            "id": 0,
            "source_path": "data/hackerrank/screen/faq.md",
            "domain": "hackerrank",
            "header": "HackerRank > screen > faq",
            "text": "To invite a candidate, go to Tests and click Invite.",
        },
        {
            "id": 1,
            "source_path": "data/claude/privacy/delete.md",
            "domain": "claude",
            "header": "Claude > privacy > delete",
            "text": "To delete a conversation, click the conversation name and select Delete.",
        },
        {
            "id": 2,
            "source_path": "data/visa/support/fraud.md",
            "domain": "visa",
            "header": "Visa > support > fraud",
            "text": "To report a stolen card, call Visa at 000-800-100-1219.",
        },
    ]
    (tmp_path / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks))
    np.save(str(tmp_path / "embeddings.npy"), np.eye(3, dtype=np.float32))
    return tmp_path


def test_bm25_returns_relevant_chunk(tmp_path: pathlib.Path) -> None:
    searcher = BM25Searcher(index_dir=_make_fake_index(tmp_path))
    results = searcher.search("how to invite a candidate", top_k=2)
    assert len(results) > 0
    assert any("invite" in r.text.lower() or "candidate" in r.text.lower() for r in results)


def test_bm25_filters_by_domain(tmp_path: pathlib.Path) -> None:
    searcher = BM25Searcher(index_dir=_make_fake_index(tmp_path))
    results = searcher.search("card stolen report", top_k=3, domain="visa")
    assert all(r.domain == "visa" for r in results)


def test_bm25_returns_all_domains_when_domain_is_none(tmp_path: pathlib.Path) -> None:
    searcher = BM25Searcher(index_dir=_make_fake_index(tmp_path))
    results = searcher.search("delete account", top_k=3, domain=None)
    domains = {r.domain for r in results}
    assert len(domains) > 1


def test_chunk_full_text_includes_header(tmp_path: pathlib.Path) -> None:
    searcher = BM25Searcher(index_dir=_make_fake_index(tmp_path))
    results = searcher.search("invite candidate", top_k=1)
    assert results[0].full_text.startswith("[Source:")


def test_empty_query_returns_empty(tmp_path: pathlib.Path) -> None:
    searcher = BM25Searcher(index_dir=_make_fake_index(tmp_path))
    results = searcher.search("", top_k=3)
    assert isinstance(results, list)
    assert results == []
