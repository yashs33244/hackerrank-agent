"""Tests for the deterministic disk cache (code/cache.py).

All cache I/O is directed at a pytest ``tmp_path`` so the real repo ``.cache``
directory is never touched.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from code import cache as cache_module
from cache import cache_key, cached_or_compute


def test_cache_key_is_deterministic_and_order_sensitive() -> None:
    """Same parts in the same order -> same key; reordering changes it."""
    assert cache_key("a", "b", "c") == cache_key("a", "b", "c")
    assert cache_key("a", "b") != cache_key("b", "a")


def test_cache_key_has_no_delimiter_collision() -> None:
    """The null-byte join means ('ab','c') and ('a','bc') do not collide."""
    assert cache_key("ab", "c") != cache_key("a", "bc")


def test_cached_or_compute_computes_on_miss(tmp_path: Path) -> None:
    """A cold key invokes ``compute`` exactly once and returns its value."""
    calls = {"count": 0}

    def compute() -> str:
        calls["count"] += 1
        return "value-x"

    out = cached_or_compute("k1", compute, cache_dir=tmp_path)

    assert out == "value-x"
    assert calls["count"] == 1
    assert (tmp_path / "k1.txt").is_file()


def test_cached_or_compute_serves_hit_without_recompute(tmp_path: Path) -> None:
    """A warm key returns the stored value and never calls ``compute`` again."""
    calls = {"count": 0}

    def compute() -> str:
        calls["count"] += 1
        return "value-y"

    first = cached_or_compute("k2", compute, cache_dir=tmp_path)
    second = cached_or_compute("k2", lambda: "SHOULD-NOT-RUN", cache_dir=tmp_path)

    assert first == second == "value-y"
    assert calls["count"] == 1


def test_unreadable_entry_recomputes(tmp_path: Path) -> None:
    """An existing entry that raises OSError on read falls back to recompute.

    We seed a real entry, then force ``Path.read_text`` to raise so the explicit
    read-failure branch (not just the cold-miss branch) is exercised.
    """
    cached_or_compute("k3", lambda: "seeded", cache_dir=tmp_path)

    with mock.patch.object(
        cache_module.Path, "read_text", side_effect=OSError("boom")
    ):
        out = cached_or_compute("k3", lambda: "recomputed", cache_dir=tmp_path)

    assert out == "recomputed"
