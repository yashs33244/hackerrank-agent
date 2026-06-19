"""Stage S3: per-attribute claim adjudication (text-only).

Compares the extracted claim against the objective per-image facts attribute by
attribute (object, part, issue, severity) and returns discrete comparison tokens
plus a falsification flag. It does NOT emit a final verdict: the deterministic
decision tree (S4) aggregates these comparisons. This separation is the documented
fix for the VLM "visual dominance" failure, where a single holistic call
rationalizes a mismatched claim and image into agreement
(see research/10_accuracy_research.md).

On a client failure it returns an empty dict, and the decision tree falls back to
its own facts-only logic, so S3 can only help, never break, a row.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import MODEL_ADJUDICATION
from domain.types import ClaimState, ExtractedClaim, ImageFact

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "adjudicate.md"

_CMP_TOKENS = {"match", "mismatch", "unknown"}
_ISSUE_TOKENS = {"match", "different_issue", "none_visible", "unknown"}


def compare_attributes(
    claim: ExtractedClaim, images: list[ImageFact], client: Any
) -> dict:
    """Compare the claim against the image facts, attribute by attribute.

    Returns a dict with keys ``object_cmp``, ``part_cmp``, ``issue_cmp``,
    ``severity_cmp``, ``supporting_image_id``, ``falsifies_claim``. On a client
    failure returns ``{}`` so the caller falls back to the deterministic
    facts-only path.
    """
    prompt = _render_prompt(claim, images)
    try:
        raw = client.run_claude_json(prompt, MODEL_ADJUDICATION, image_paths=None)
    except client.ClaudeError:
        return {}
    return _normalize(raw)


def adjudicate_state(state: ClaimState, client: Any) -> dict:
    """Convenience wrapper that adjudicates a fully populated ``ClaimState``."""
    if state.claim is None:
        return {}
    return compare_attributes(state.claim, state.images, client)


def _normalize(raw: dict) -> dict:
    """Clamp the model output to the known comparison tokens, defaulting unknown."""

    def _cmp(value: Any, allowed: set[str]) -> str:
        token = str(value).strip().lower()
        return token if token in allowed else "unknown"

    return {
        "object_cmp": _cmp(raw.get("object_cmp"), _CMP_TOKENS),
        "part_cmp": _cmp(raw.get("part_cmp"), _CMP_TOKENS),
        "issue_cmp": _cmp(raw.get("issue_cmp"), _ISSUE_TOKENS),
        "severity_cmp": _cmp(raw.get("severity_cmp"), _CMP_TOKENS),
        "supporting_image_id": str(raw.get("supporting_image_id", "none")).strip(),
        "falsifies_claim": bool(raw.get("falsifies_claim", False)),
    }


def _render_prompt(claim: ExtractedClaim, images: list[ImageFact]) -> str:
    """Fill the comparison template with JSON of the claim and image facts.
    Literal replacement is used because the template contains JSON braces."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    claim_json = json.dumps(asdict(claim))
    facts_json = json.dumps([asdict(fact) for fact in images])
    return template.replace("{claim_json}", claim_json).replace(
        "{image_facts_json}", facts_json
    )
