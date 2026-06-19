"""Claude Code headless client: the single inference choke point.

Every model call in the pipeline goes through here. There is NO API key: we
shell out to the installed ``claude`` CLI in print mode, authenticated by the
user's subscription (research/06_self_grill.md D1). The command is built so the
nested ``claude`` runs from a neutral temp directory and therefore does NOT load
this repo's AGENTS.md, which would otherwise contaminate the inner agent with
the contest's logging contract.

Public contract (consumers import these names and rely on the exact behaviour):

    class ClaudeError(RuntimeError): ...
    run_claude_text(prompt, model, image_paths=None, system=None,
                    timeout=None, max_retries=2) -> str
    run_claude_json(prompt, model, image_paths=None, system=None,
                    timeout=None, max_retries=2) -> dict

``subprocess``, ``tempfile``, and ``time`` are referenced as module attributes
(not ``from`` imports) so tests can patch them, and ``CLAUDE_BIN`` / ``CACHE_DIR``
are bound at module scope for the same reason.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

from cache import cache_key, cached_or_compute
from config import CACHE_DIR, CLAUDE_BIN, CLAUDE_TIMEOUT_S

# Re-exported at module scope so tests/consumers can patch the effective values
# without reaching into ``code.config``.
CLAUDE_BIN = CLAUDE_BIN
CACHE_DIR = CACHE_DIR

# Backoff base in seconds; the nth retry sleeps ``_BACKOFF_BASE_S * 2**(n-1)``.
_BACKOFF_BASE_S: float = 1.0


class ClaudeError(RuntimeError):
    """Raised when a ``claude`` invocation fails after exhausting retries."""


def run_claude_text(
    prompt: str,
    model: str,
    image_paths: list[str] | None = None,
    system: str | None = None,
    timeout: int | None = None,
    max_retries: int = 2,
) -> str:
    """Run one headless ``claude`` call and return the envelope ``result`` text.

    Retries on nonzero exit, timeout, or an ``is_error`` envelope, with
    exponential backoff, up to ``max_retries`` extra attempts. Raises
    ``ClaudeError`` once all attempts are spent.
    """
    command = _build_command(prompt, model, image_paths, system)
    return _invoke_with_retries(command, timeout, max_retries)


def run_claude_json(
    prompt: str,
    model: str,
    image_paths: list[str] | None = None,
    system: str | None = None,
    timeout: int | None = None,
    max_retries: int = 2,
) -> dict:
    """Run a headless ``claude`` call and parse its result as a JSON object.

    When ``image_paths`` is given, the parsed result is memoized on disk keyed
    by model + prompt + image content hashes, so re-runs and repeated images
    never re-pay the call. On a parse failure the call is retried once with an
    explicit "return only valid JSON" nudge before raising ``ClaudeError``.
    """
    if image_paths:
        key = cache_key(
            "claude_json",
            model,
            prompt,
            system or "",
            *_image_content_hashes(image_paths),
        )
        raw = cached_or_compute(
            key,
            lambda: json.dumps(
                _run_json_uncached(
                    prompt, model, image_paths, system, timeout, max_retries
                )
            ),
            cache_dir=CACHE_DIR,
        )
        return json.loads(raw)

    return _run_json_uncached(
        prompt, model, image_paths, system, timeout, max_retries
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _run_json_uncached(
    prompt: str,
    model: str,
    image_paths: list[str] | None,
    system: str | None,
    timeout: int | None,
    max_retries: int,
) -> dict:
    """Run the call and parse JSON, with one corrective JSON-nudge retry."""
    text = run_claude_text(prompt, model, image_paths, system, timeout, max_retries)
    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed

    nudge_prompt = (
        f"{prompt}\n\nReturn ONLY valid JSON. No prose, no code fences, "
        "just a single JSON object."
    )
    retry_text = run_claude_text(
        nudge_prompt, model, image_paths, system, timeout, max_retries
    )
    parsed = _try_parse_json(retry_text)
    if parsed is not None:
        return parsed

    raise ClaudeError(
        "claude returned text that could not be parsed as JSON after a retry"
    )


def _build_command(
    prompt: str,
    model: str,
    image_paths: list[str] | None,
    system: str | None,
) -> list[str]:
    """Assemble the ``claude`` argv. Order is fixed and asserted by tests."""
    command: list[str] = [
        CLAUDE_BIN,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--model",
        model,
        "--allowedTools",
        "Read",
    ]
    for directory in _unique_parent_dirs(image_paths):
        command += ["--add-dir", directory]
    if system:
        command += ["--append-system-prompt", system]
    return command


def _unique_parent_dirs(image_paths: list[str] | None) -> list[str]:
    """Absolute, de-duplicated parent directories of the supplied images.

    The nested ``claude`` needs each image's directory granted via ``--add-dir``
    to read it. Order is stabilized (sorted) so an identical image set always
    produces an identical command, which keeps the cache key stable too.
    """
    if not image_paths:
        return []
    parents: set[str] = set()
    for path in image_paths:
        parents.add(str(Path(path).resolve().parent))
    return sorted(parents)


def _invoke_with_retries(
    command: list[str], timeout: int | None, max_retries: int
) -> str:
    """Run ``command``, retrying on failure with exponential backoff.

    Returns the envelope ``result`` string on success. Raises ``ClaudeError``
    after ``max_retries`` extra attempts. ``time.sleep`` is patched out in tests.
    """
    effective_timeout = timeout if timeout is not None else CLAUDE_TIMEOUT_S
    last_error: str = "unknown error"

    for attempt in range(max_retries + 1):
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=tempfile.mkdtemp(),
            )
        except subprocess.TimeoutExpired:
            last_error = f"timed out after {effective_timeout}s"
            _backoff(attempt, max_retries)
            continue
        except OSError as error:
            # e.g. claude binary not found; not worth retrying but stay uniform.
            last_error = f"failed to launch claude: {error}"
            _backoff(attempt, max_retries)
            continue

        if completed.returncode != 0:
            last_error = (
                f"claude exited {completed.returncode}: "
                f"{(completed.stderr or '').strip()[:200]}"
            )
            _backoff(attempt, max_retries)
            continue

        result, is_error = _parse_envelope(completed.stdout)
        if is_error:
            last_error = f"claude reported is_error=true: {result[:200]}"
            _backoff(attempt, max_retries)
            continue

        return result

    raise ClaudeError(
        f"claude call failed after {max_retries + 1} attempts: {last_error}"
    )


def _backoff(attempt: int, max_retries: int) -> None:
    """Sleep with exponential backoff, unless this was the final attempt."""
    if attempt < max_retries:
        time.sleep(_BACKOFF_BASE_S * (2 ** attempt))


def _parse_envelope(stdout: str) -> tuple[str, bool]:
    """Extract ``(result, is_error)`` from the Claude Code JSON envelope.

    A malformed or empty envelope is treated as an error so the caller retries
    rather than silently returning garbage.
    """
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return ("envelope was not valid JSON", True)

    if not isinstance(envelope, dict):
        return ("envelope was not a JSON object", True)

    result = envelope.get("result", "")
    is_error = bool(envelope.get("is_error", False))
    if not isinstance(result, str):
        result = json.dumps(result)
    return (result, is_error)


def _try_parse_json(text: str) -> dict | None:
    """Best-effort parse of a JSON object out of ``text``.

    Strips ```json fences, then loads the first balanced ``{...}`` block. Returns
    ``None`` (never raises) when no object can be recovered, so the caller can
    decide whether to nudge-and-retry or give up.
    """
    cleaned = _strip_code_fences(text).strip()

    # Fast path: the whole string is one JSON object.
    try:
        loaded = json.loads(cleaned)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass

    block = _first_balanced_object(cleaned)
    if block is None:
        return None
    try:
        loaded = json.loads(block)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _strip_code_fences(text: str) -> str:
    """Remove a leading ```json / ``` fence and trailing ``` if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    # Drop the opening fence line (``` or ```json) and a trailing fence.
    newline = stripped.find("\n")
    body = stripped[newline + 1 :] if newline != -1 else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[: -len("```")]
    return body


def _first_balanced_object(text: str) -> str | None:
    """Return the first brace-balanced ``{...}`` substring, or ``None``.

    String-aware so a ``}`` inside a quoted value never closes the object early.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    is_escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if is_escaped:
                is_escaped = False
            elif char == "\\":
                is_escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _image_content_hashes(image_paths: list[str]) -> list[str]:
    """Stable content hashes of each image, sorted, for cache keying.

    Hashing the bytes (not the path) means the cache survives a file move and,
    more importantly, two byte-identical images share one cache entry. A missing
    or unreadable image hashes its path instead so the key stays deterministic
    and the call still proceeds (the model layer surfaces the real failure).
    """
    hashes: list[str] = []
    for path in image_paths:
        try:
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            digest = "missing:" + hashlib.sha256(path.encode("utf-8")).hexdigest()
        hashes.append(digest)
    return sorted(hashes)
