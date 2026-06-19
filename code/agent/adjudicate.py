"""Stage S3: adjudication (text-only).

Drafts the ten produced columns by reasoning over the per-image facts, the
extracted claim, the applicable evidence rule, and the user history. No image is
attached here: a prior stage already perceived each image. A deterministic
post-processor (S4) finalizes every enum afterward, so this draft is a proposal,
not the final word.

On a client failure the function returns a conservative
``not_enough_information`` draft that also routes the row to manual review.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import MODEL_ADJUDICATION
from domain.types import ClaimState

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "adjudicate.md"


def adjudicate(state: ClaimState, client: Any) -> dict:
    """Draft the ten produced columns for one claim, text-only.

    Args:
        state: The per-row state, already carrying the extracted claim,
            per-image facts, evidence rule, and history.
        client: A module/object exposing ``run_claude_json`` and ``ClaudeError``.

    Returns:
        A draft dict of the ten produced columns. On a client failure, a safe
        ``not_enough_information`` draft flagged for manual review.
    """
    prompt = _render_prompt(state)
    try:
        # image_paths is None: adjudication reasons over facts, never pixels.
        draft = client.run_claude_json(prompt, MODEL_ADJUDICATION, image_paths=None)
    except client.ClaudeError:
        return _safe_default_draft()

    return _normalize_draft(draft)


def _normalize_draft(draft: dict) -> dict:
    """Fill any field the model omitted with a conservative default so every
    downstream consumer sees all ten keys. WHY: the deterministic tree indexes
    these keys directly and must never KeyError on a partial model response."""
    return {
        "evidence_standard_met": draft.get("evidence_standard_met", False),
        "evidence_standard_met_reason": str(
            draft.get("evidence_standard_met_reason", "")
        ),
        "risk_flags": _as_str_list(draft.get("risk_flags")),
        "issue_type": str(draft.get("issue_type", "unknown")),
        "object_part": str(draft.get("object_part", "unknown")),
        "claim_status": str(draft.get("claim_status", "not_enough_information")),
        "claim_status_justification": str(
            draft.get("claim_status_justification", "")
        ),
        "supporting_image_ids": _as_str_list(draft.get("supporting_image_ids")),
        "valid_image": draft.get("valid_image", True),
        "severity": str(draft.get("severity", "unknown")),
    }


def _safe_default_draft() -> dict:
    """The draft emitted when adjudication fails: abstain and ask for a human.

    Mirrors the pipeline's "when in doubt -> not_enough_information +
    manual_review_required" rule rather than guessing a verdict.
    """
    return {
        "evidence_standard_met": False,
        "evidence_standard_met_reason": "Adjudication failed; routed to manual review.",
        "risk_flags": ["manual_review_required"],
        "issue_type": "unknown",
        "object_part": "unknown",
        "claim_status": "not_enough_information",
        "claim_status_justification": "Could not adjudicate this claim automatically.",
        "supporting_image_ids": [],
        "valid_image": True,
        "severity": "unknown",
    }


def _render_prompt(state: ClaimState) -> str:
    """Fill the adjudication template with JSON blobs of the state slices.
    Literal replacement is used because the template contains JSON braces."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{claim_json}", _claim_json(state))
        .replace("{image_facts_json}", _image_facts_json(state))
        .replace("{evidence_rule_json}", _evidence_rule_json(state))
        .replace("{history_json}", _history_json(state))
    )


def _claim_json(state: ClaimState) -> str:
    return json.dumps(asdict(state.claim)) if state.claim else "{}"


def _image_facts_json(state: ClaimState) -> str:
    return json.dumps([asdict(fact) for fact in state.images])


def _evidence_rule_json(state: ClaimState) -> str:
    return json.dumps(asdict(state.evidence_rule)) if state.evidence_rule else "{}"


def _history_json(state: ClaimState) -> str:
    return json.dumps(asdict(state.history)) if state.history else "{}"


def _as_str_list(value: Any) -> list[str]:
    """Coerce a JSON value to a list of strings; non-lists -> empty list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
