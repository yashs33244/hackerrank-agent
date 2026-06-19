"""Stage S2: per-image perception.

One ``claude`` vision call per image. The image is the primary source of truth,
so this stage only reports what is visually observable (describe before decide)
and never adjudicates the claim. The prompt carries the untrusted-text guardrail
so in-image instructions are transcribed as data, never obeyed.

On any client failure the function returns a conservative ``ImageFact`` marked
undecodable and irrelevant, so a single bad image can never crash the batch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import MODEL_PERCEPTION
from domain.types import ExtractedClaim, ImageFact

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "perception.md"


def perceive_image(
    image_path: str,
    image_id: str,
    claim: ExtractedClaim,
    client: Any,
) -> ImageFact:
    """Inspect one image and return its structured ``ImageFact``.

    Args:
        image_path: Path to the (already normalized) image file to read.
        image_id: The image's id (filename without extension, e.g. ``img_2``),
            injected into the prompt so the model knows which image it is reading.
        claim: The extracted claim, supplied as untrusted context only.
        client: A module/object exposing ``run_claude_json`` and ``ClaudeError``.
            Injected so tests pass a fake and no real subprocess is spawned.

    Returns:
        An ``ImageFact`` populated from the model's JSON. On a client failure a
        safe default (undecodable, irrelevant, zero confidence) is returned.
    """
    # The client grants the image's directory via --add-dir, but the model still
    # needs to be told which file to open. Naming the absolute path and asking for
    # the Read tool explicitly is what makes the vision call actually inspect it.
    prompt = (
        f"Use the Read tool to open the image file at {image_path}, then analyze "
        f"it as described below.\n\n" + _render_prompt(image_id=image_id, claim=claim)
    )
    try:
        payload = client.run_claude_json(
            prompt,
            MODEL_PERCEPTION,
            image_paths=[image_path],
        )
    except client.ClaudeError:
        # Conservative default: the downstream tree treats this image as unusable
        # rather than fabricating a perception. WHY: a hallucinated fact is worse
        # than an explicit "could not read this image".
        return _safe_default(image_path, image_id)

    return _fact_from_payload(payload, image_path, image_id)


def _fact_from_payload(payload: dict, image_path: str, image_id: str) -> ImageFact:
    """Map the model's JSON object onto an ``ImageFact``, defaulting any field
    the model omitted. The model's own ``image_id`` is ignored in favor of the
    one we assigned, so a confused model can never relabel an image."""
    return ImageFact(
        image_id=image_id,
        path=image_path,
        image_format=str(payload.get("image_format", "")),
        decodable=_as_bool(payload.get("decodable"), default=True),
        # Normalize enum-like tokens to lowercase at the boundary: vision models
        # often return "Car"/"Dent"/"High", and the deterministic tree matches
        # tokens case-sensitively, so an un-normalized capital silently collapses
        # to unknown (or flips a verdict to contradicted).
        shown_object=str(payload.get("shown_object", "unknown")).strip().lower(),
        shown_part=str(payload.get("shown_part", "unknown")).strip().lower(),
        has_visible_damage=_as_bool(payload.get("has_visible_damage"), default=False),
        issue_guess=str(payload.get("issue_guess", "unknown")).strip().lower(),
        severity_guess=str(payload.get("severity_guess", "unknown")).strip().lower(),
        quality_issues=_as_str_list(payload.get("quality_issues")),
        embedded_text=str(payload.get("embedded_text", "")),
        text_is_instruction=_as_bool(payload.get("text_is_instruction"), default=False),
        authenticity_notes=str(payload.get("authenticity_notes", "")),
        non_original=_as_bool(payload.get("non_original"), default=False),
        possible_manipulation=_as_bool(
            payload.get("possible_manipulation"), default=False
        ),
        is_relevant_to_claim=_as_bool(
            payload.get("is_relevant_to_claim"), default=False
        ),
        is_clear_enough=_as_bool(payload.get("is_clear_enough"), default=False),
        confidence=_as_float(payload.get("confidence")),
    )


def _safe_default(image_path: str, image_id: str) -> ImageFact:
    """The fact emitted when the vision call fails outright."""
    return ImageFact(
        image_id=image_id,
        path=image_path,
        image_format="",
        decodable=False,
        is_relevant_to_claim=False,
        is_clear_enough=False,
        confidence=0.0,
    )


def _render_prompt(image_id: str, claim: ExtractedClaim) -> str:
    """Fill the perception template. Uses literal replacement (not ``str.format``)
    because the template contains JSON braces that ``format`` would choke on."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    # Claim-aware for part identification (improves object_part), but the prompt
    # instructs the model to treat the claim only as a pointer and verify damage
    # independently (curbs the case_008/case_014 sycophancy).
    claim_summary = (
        f"part={claim.claimed_part}, issue={claim.claimed_issue}, "
        f"severity={claim.claimed_severity_word}"
    )
    return (
        template.replace("{image_id}", image_id)
        .replace("{claim_object}", claim.claimed_object)
        .replace("{claim_summary}", claim_summary)
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


def _as_float(value: Any) -> float:
    """Coerce a JSON value to a float in [0.0, 1.0]; malformed input -> 0.0."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, result))


def _as_str_list(value: Any) -> list[str]:
    """Coerce a JSON value to a list of strings; non-lists -> empty list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
