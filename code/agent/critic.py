"""Stage S5: critic / validator.

Validates an adjudication draft against the facts that produced it. It is rules-
first: grounding (does the justification cite a real inspected image?), coherence
(NEI implies no supporting ids and unknown severity, etc.), enum legality, and an
injection echo-check (did the verdict parrot in-image instructions?).

On a client failure the function does not block the row: it marks the draft as
invalid-but-safe and requests manual review, so a flaky critic never silently
approves a bad verdict nor crashes the batch.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import MODEL_CRITIC
from domain.types import ClaimState

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "critic.md"


def critique(draft: dict, state: ClaimState, client: Any) -> dict:
    """Validate an adjudication draft.

    Args:
        draft: The ten-column draft produced by ``adjudicate``.
        state: The per-row state (claim + per-image facts) the draft came from.
        client: A module/object exposing ``run_claude_json`` and ``ClaudeError``.

    Returns:
        A validation dict with keys ``is_valid``, ``issues``, ``injection_echo``,
        ``needs_manual_review``, and ``corrected``. On a client failure, a safe
        result that marks the draft invalid and requests manual review.
    """
    prompt = _render_prompt(draft, state)
    try:
        result = client.run_claude_json(prompt, MODEL_CRITIC)
    except client.ClaudeError:
        return _safe_default_result()

    return _normalize_result(result)


def _normalize_result(result: dict) -> dict:
    """Fill any field the critic omitted with a conservative default so callers
    always see the full validation shape."""
    return {
        "is_valid": _as_bool(result.get("is_valid"), default=False),
        "issues": _as_str_list(result.get("issues")),
        "injection_echo": _as_bool(result.get("injection_echo"), default=False),
        "needs_manual_review": _as_bool(
            result.get("needs_manual_review"), default=False
        ),
        "corrected": result.get("corrected") if isinstance(result.get("corrected"), dict) else {},
    }


def _safe_default_result() -> dict:
    """The result emitted when the critic call fails: do not approve blindly."""
    return {
        "is_valid": False,
        "issues": ["critic call failed; routed to manual review"],
        "injection_echo": False,
        "needs_manual_review": True,
        "corrected": {},
    }


def _render_prompt(draft: dict, state: ClaimState) -> str:
    """Fill the critic template with JSON blobs of the draft, claim, and facts.
    Literal replacement is used because the template contains JSON braces."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    claim_json = json.dumps(asdict(state.claim)) if state.claim else "{}"
    facts_json = json.dumps([asdict(fact) for fact in state.images])
    return (
        template.replace("{draft_json}", json.dumps(draft))
        .replace("{claim_json}", claim_json)
        .replace("{image_facts_json}", facts_json)
    )


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce a JSON value to bool, tolerating string ``true``/``false``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    if value is None:
        return default
    return bool(value)


def _as_str_list(value: Any) -> list[str]:
    """Coerce a JSON value to a list of strings; non-lists -> empty list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
