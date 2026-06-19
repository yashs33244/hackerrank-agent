"""Tiny deterministic disk cache.

Keyed by a sha256 of caller-supplied parts; values are UTF-8 text stored one
file per key under ``CACHE_DIR``. The point is cost: model calls (especially
vision over the 111 images) are expensive against the subscription usage
window, so an identical re-run or a repeated image is served from disk for free.

Cache writes are atomic (write to a temp file, then rename) so a crashed run
never leaves a half-written, corrupt cache entry behind.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from config import CACHE_DIR as DEFAULT_CACHE_DIR


def cache_key(*parts: str) -> str:
    """Return a stable sha256 hex digest over ``parts``.

    Parts are joined with a null byte so that ``("ab", "c")`` and ``("a", "bc")``
    never collide. Order is significant, which is what every caller wants
    (model name, then prompt, then image hashes).
    """
    hasher = hashlib.sha256()
    for index, part in enumerate(parts):
        if index:
            hasher.update(b"\x00")
        hasher.update(part.encode("utf-8"))
    return hasher.hexdigest()


def _path_for(key: str, cache_dir: Path | str) -> Path:
    """Filesystem path of the cache entry for ``key`` under ``cache_dir``."""
    return Path(cache_dir) / f"{key}.txt"


def cached_or_compute(
    key: str,
    compute: Callable[[], str],
    cache_dir: Path | str | None = None,
) -> str:
    """Return the cached value for ``key`` or compute, store, and return it.

    ``compute`` is only invoked on a cache miss. ``cache_dir`` defaults to the
    configured ``CACHE_DIR`` but callers may pass their own so the storage
    location stays in their control (and patchable in tests). Any failure to
    read the cache (corrupt file, permission error) degrades gracefully to a
    recompute rather than crashing the pipeline, since the cache is a pure
    optimization.
    """
    directory = DEFAULT_CACHE_DIR if cache_dir is None else cache_dir
    entry = _path_for(key, directory)
    if entry.is_file():
        try:
            return entry.read_text(encoding="utf-8")
        except OSError:
            # Unreadable cache entry: fall through and recompute below.
            pass

    value = compute()
    _store(entry, value)
    return value


def _store(entry: Path, value: str) -> None:
    """Atomically write ``value`` to ``entry``, creating parents as needed.

    A write failure is swallowed: a missing cache entry only costs a recompute
    next time, so it must never break the run that produced the value.
    """
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=str(entry.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
            os.replace(temp_name, entry)
        finally:
            # If the rename already happened this unlink is a harmless no-op.
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    except OSError:
        return
