"""Stage S1: claim extraction.

One cheap text call that parses the (possibly multilingual) support conversation
into a normalized ``ExtractedClaim``. The conversation is the question, not the
answer: later stages judge the pixels, so this stage only records what the
customer is claiming.

On a client failure the function falls back to the known ``claim_object`` with
everything else ``unknown``, so the row still flows through the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import MODEL_CLAIM_EXTRACT
from domain.types import ExtractedClaim

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "claim_extract.md"


def extract_claim(
    user_claim: str,
    claim_object: str,
    client: Any,
) -> ExtractedClaim:
    """Parse a support conversation into a structured claim.

    Args:
        user_claim: The full conversation transcript (any language). Passed to
            the model verbatim so multilingual content is preserved.
        claim_object: The known object token from the dataset (car/laptop/
            package), used as the default and as a sanity anchor.
        client: A module/object exposing ``run_claude_json`` and ``ClaudeError``.

    Returns:
        An ``ExtractedClaim``. On a client failure, a safe default keyed on the
        known ``claim_object`` with all other fields ``unknown``.
    """
    prompt = _render_prompt(user_claim=user_claim, claim_object=claim_object)
    try:
        payload = client.run_claude_json(prompt, MODEL_CLAIM_EXTRACT)
    except client.ClaudeError:
        return _safe_default(claim_object)

    return _claim_from_payload(payload, claim_object)


def _claim_from_payload(payload: dict, claim_object: str) -> ExtractedClaim:
    """Map the model JSON onto an ``ExtractedClaim``, defaulting omitted fields.
    ``claimed_object`` falls back to the dataset-provided object so the extraction
    can never silently lose the object type."""
    return ExtractedClaim(
        claimed_object=str(payload.get("claimed_object") or claim_object),
        claimed_part=str(payload.get("claimed_part", "unknown")),
        claimed_issue=str(payload.get("claimed_issue", "unknown")),
        claimed_severity_word=str(payload.get("claimed_severity_word", "unknown")),
        missing_item=_as_bool(payload.get("missing_item")),
        secondary_parts=_as_str_list(payload.get("secondary_parts")),
        language=str(payload.get("language", "en")),
    )


def _safe_default(claim_object: str) -> ExtractedClaim:
    """The claim emitted when extraction fails: keep the object, abstain on rest."""
    return ExtractedClaim(
        claimed_object=claim_object,
        claimed_part="unknown",
        claimed_issue="unknown",
        claimed_severity_word="unknown",
    )


def _render_prompt(user_claim: str, claim_object: str) -> str:
    """Fill the extraction template via literal replacement (the template holds
    JSON braces that ``str.format`` would mishandle)."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{claim_object}", claim_object).replace(
        "{user_claim}", user_claim
    )


def _as_bool(value: Any) -> bool:
    """Coerce a JSON value to bool, tolerating string ``true``/``false``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _as_str_list(value: Any) -> list[str]:
    """Coerce a JSON value to a list of strings; non-lists -> empty list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
