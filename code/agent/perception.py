"""Stage S2: per-image perception.

One ``claude`` vision call per image. The image is the primary source of truth,
so this stage only reports what is visually observable (describe before decide)
and never adjudicates the claim. The prompt carries the untrusted-text guardrail
so in-image instructions are transcribed as data, never obeyed.

On any client failure the function returns a conservative ``ImageFact`` marked
undecodable and irrelevant, so a single bad image can never crash the batch.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from config import MODEL_PERCEPTION, PERCEPTION_CLAIM_BLIND
from domain.types import ExtractedClaim, ImageFact

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_PATH = _PROMPTS_DIR / "perception.md"
_BLIND_PROMPT_PATH = _PROMPTS_DIR / "perception_blind.md"


def perceive_image(
    image_path: str,
    image_id: str,
    claim: ExtractedClaim,
    client: Any,
    samples: int = 1,
) -> ImageFact:
    """Inspect one image and return its structured ``ImageFact``.

    With ``samples > 1`` the image is read independently that many times and each
    field is decided by majority vote (self-consistency). Vision reads are not
    temperature-zero, so a single read is noisy; majority voting both denoises the
    facts (fewer flipped verdicts) and makes the result far more reproducible
    (research/10_accuracy_research.md, #5).

    Args:
        image_path: Path to the (already normalized) image file to read.
        image_id: The image's id (filename without extension, e.g. ``img_2``).
        claim: The extracted claim, supplied as untrusted context only.
        client: A module/object exposing ``run_claude_json`` and ``ClaudeError``.
        samples: Number of independent reads to majority-vote (1 = single read).

    Returns:
        An ``ImageFact``. On total client failure a safe default (undecodable,
        irrelevant, zero confidence) is returned.
    """
    # The client grants the image's directory via --add-dir, but the model still
    # needs to be told which file to open. Naming the absolute path and asking for
    # the Read tool explicitly is what makes the vision call actually inspect it.
    base_prompt = (
        f"Use the Read tool to open the image file at {image_path}, then analyze "
        f"it as described below.\n\n" + _render_prompt(image_id=image_id, claim=claim)
    )
    payloads = _read_payloads(base_prompt, image_path, client, max(1, samples))
    if not payloads:
        return _safe_default(image_path, image_id)
    payload = payloads[0] if len(payloads) == 1 else _majority_payload(payloads)
    return _fact_from_payload(payload, image_path, image_id)


def _read_payloads(
    base_prompt: str, image_path: str, client: Any, samples: int
) -> list[dict]:
    """Read the image ``samples`` times, returning each parsed payload. A nonce per
    pass keeps the reads independent (distinct cache keys); failed reads are skipped
    so a single transient error never sinks the vote."""
    payloads: list[dict] = []
    for index in range(samples):
        prompt = base_prompt
        if samples > 1:
            prompt = f"{base_prompt}\n\n(Independent reading {index + 1} of {samples}.)"
        try:
            payloads.append(
                client.run_claude_json(prompt, MODEL_PERCEPTION, image_paths=[image_path])
            )
        except client.ClaudeError:
            continue
    return payloads


def _majority_payload(payloads: list[dict]) -> dict:
    """Combine several independent reads of one image into a single consensus
    payload by majority vote per field. Categorical fields take the mode; booleans
    take a strict majority; a quality issue is kept only if a majority reported it;
    confidence is averaged. This is what removes the single-read noise."""
    def _mode(key: str, default: str) -> str:
        values = [str(p.get(key, default)).strip().lower() for p in payloads]
        return Counter(values).most_common(1)[0][0]

    def _majority_bool(key: str) -> bool:
        votes = [_as_bool(p.get(key), False) for p in payloads]
        return sum(votes) * 2 > len(votes)

    def _first_nonempty(key: str) -> str:
        return next((str(p.get(key, "")) for p in payloads if p.get(key)), "")

    quality_counts: Counter = Counter()
    for payload in payloads:
        for issue in set(_as_str_list(payload.get("quality_issues"))):
            quality_counts[issue] += 1
    quality = [q for q, c in quality_counts.items() if c * 2 > len(payloads)]
    confidence = sum(_as_float(p.get("confidence")) for p in payloads) / len(payloads)

    return {
        "shown_object": _mode("shown_object", "unknown"),
        "shown_part": _mode("shown_part", "unknown"),
        "has_visible_damage": _majority_bool("has_visible_damage"),
        "issue_guess": _mode("issue_guess", "unknown"),
        "severity_guess": _mode("severity_guess", "unknown"),
        "quality_issues": quality,
        "embedded_text": _first_nonempty("embedded_text"),
        "text_is_instruction": _majority_bool("text_is_instruction"),
        "authenticity_notes": _first_nonempty("authenticity_notes"),
        "non_original": _majority_bool("non_original"),
        "possible_manipulation": _majority_bool("possible_manipulation"),
        "is_relevant_to_claim": _majority_bool("is_relevant_to_claim"),
        "is_clear_enough": _majority_bool("is_clear_enough"),
        "confidence": confidence,
    }


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
    because the template contains JSON braces that ``format`` would choke on.

    Two modes (config.PERCEPTION_CLAIM_BLIND): the claim-blind template never names
    the claimed part/issue/severity, so the model reports the damage it actually
    sees (curbs the affirmative-bias contradicted-recall miss); the claim-aware
    template passes the claim as a pointer only. Both receive the case object type
    so a wrong-object image can still be flagged."""
    if PERCEPTION_CLAIM_BLIND:
        template = _BLIND_PROMPT_PATH.read_text(encoding="utf-8")
        return template.replace("{image_id}", image_id).replace(
            "{claim_object}", claim.claimed_object
        )
    template = _PROMPT_PATH.read_text(encoding="utf-8")
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
