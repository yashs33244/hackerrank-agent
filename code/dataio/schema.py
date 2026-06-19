"""Pydantic v2 output schema and the clamp that makes model output legal.

The adjudicating model proposes the ten produced columns as free-form JSON. That
JSON is never trusted: ``coerce_output`` repairs every illegal token into a legal
one and never raises. This guarantees the final CSV contains zero invalid enum
values regardless of what the model returns, which is the single highest-leverage
robustness property of the whole pipeline.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from domain.constants import (
    NONE_TOKEN,
    OBJECT_PART_VOCAB,
    RISK_FLAG_CANONICAL_ORDER,
)
from domain.enums import (
    ClaimStatus,
    IssueType,
    RiskFlag,
    Severity,
)

# Legal token sets, computed once. Membership checks drive every clamp below.
_CLAIM_STATUS_VOCAB: frozenset[str] = frozenset(s.value for s in ClaimStatus)
_ISSUE_TYPE_VOCAB: frozenset[str] = frozenset(i.value for i in IssueType)
_SEVERITY_VOCAB: frozenset[str] = frozenset(s.value for s in Severity)
_RISK_FLAG_VOCAB: frozenset[str] = frozenset(f.value for f in RiskFlag)

# Canonical sort key for risk_flags so the same set always serializes identically.
_RISK_FLAG_RANK: dict[str, int] = {
    flag: index for index, flag in enumerate(RISK_FLAG_CANONICAL_ORDER)
}

# Safe fallbacks used when the model omits or mangles a field. These mirror the
# "when in doubt, abstain" policy (D9/D10): an unknown row is treated as
# not-enough-information rather than silently asserted as supported.
_FALLBACK_CLAIM_STATUS = ClaimStatus.NOT_ENOUGH_INFORMATION.value
_FALLBACK_ISSUE_TYPE = IssueType.UNKNOWN.value
_FALLBACK_SEVERITY = Severity.UNKNOWN.value
_FALLBACK_OBJECT_PART = "unknown"


class OutputRow(BaseModel):
    """One fully validated output row: 4 echoed inputs + 10 produced columns.

    Field names match ``OUTPUT_COLUMNS`` exactly so the formatter can read them
    by attribute. Values are already clamped to legal tokens by the time an
    instance exists, so the model is a guarantee, not just a container.
    """

    model_config = ConfigDict(frozen=True)

    # Echoed input columns (verbatim from claims.csv).
    user_id: str = ""
    image_paths: str = ""
    user_claim: str = ""
    claim_object: str = ""

    # Produced columns.
    evidence_standard_met: bool = False
    evidence_standard_met_reason: str = ""
    risk_flags: list[str] = [NONE_TOKEN]
    issue_type: str = _FALLBACK_ISSUE_TYPE
    object_part: str = _FALLBACK_OBJECT_PART
    claim_status: str = _FALLBACK_CLAIM_STATUS
    claim_status_justification: str = ""
    supporting_image_ids: list[str] = []
    valid_image: bool = False
    severity: str = _FALLBACK_SEVERITY


def _as_bool(value: Any, *, default: bool = False) -> bool:
    """Coerce loose truthy/falsey model output into a strict bool.

    Models sometimes emit the strings ``"true"``/``"false"`` instead of JSON
    booleans; treat those (and obvious numeric forms) sensibly, default otherwise.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0", ""}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_text(value: Any) -> str:
    """Coerce a scalar field to a stripped string; None and missing become ''."""
    if value is None:
        return ""
    return str(value).strip()


def _bare_image_id(token: str) -> str:
    """Reduce a path or filename to a bare image ID (``img_2``).

    Drops any directory prefix and the file extension so the CSV never leaks a
    path or extension into ``supporting_image_ids``.
    """
    name = token.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0].strip()


def _clamp_enum(value: Any, vocab: frozenset[str], fallback: str) -> str:
    """Return ``value`` if it is a legal token, else the fallback token."""
    text = _as_text(value).lower()
    return text if text in vocab else fallback


def _clamp_object_part(value: Any, claim_object: str) -> str:
    """Clamp ``object_part`` to the vocabulary of the given ``claim_object``.

    A laptop can never carry a car part, so any token outside this object's
    allowed set collapses to ``unknown`` (D15).
    """
    allowed = OBJECT_PART_VOCAB.get(_as_text(claim_object).lower())
    if allowed is None:
        return _FALLBACK_OBJECT_PART
    text = _as_text(value).lower()
    return text if text in allowed else _FALLBACK_OBJECT_PART


def _clamp_risk_flags(value: Any) -> list[str]:
    """Filter to legal flags, drop ``none`` when real flags exist, dedupe, order.

    Empty (or all-illegal) input collapses to the single ``["none"]`` literal so
    the column is never blank (D12).
    """
    if not isinstance(value, (list, tuple, set)):
        value = [value] if value not in (None, "") else []

    legal: set[str] = set()
    for raw_flag in value:
        token = _as_text(raw_flag).lower()
        if token in _RISK_FLAG_VOCAB:
            legal.add(token)

    # 'none' only means something when it is the *only* flag.
    real_flags = legal - {NONE_TOKEN}
    if real_flags:
        return sorted(real_flags, key=lambda f: _RISK_FLAG_RANK[f])
    return [NONE_TOKEN]


def _clamp_supporting_ids(value: Any) -> list[str]:
    """Reduce supporting IDs to bare, de-duplicated, order-preserving tokens."""
    if not isinstance(value, (list, tuple, set)):
        value = [value] if value not in (None, "") else []

    seen: set[str] = set()
    result: list[str] = []
    for raw_id in value:
        bare = _bare_image_id(_as_text(raw_id))
        if bare and bare != NONE_TOKEN and bare not in seen:
            seen.add(bare)
            result.append(bare)
    return result


def coerce_output(raw: dict[str, Any], claim_object: str) -> OutputRow:
    """Build a fully legal :class:`OutputRow` from untrusted model output.

    Every illegal enum is clamped to a legal token, ``object_part`` is forced
    into the vocabulary of ``claim_object``, illegal risk flags are dropped, and
    empty risk flags become ``["none"]``. This function never raises on bad input
    by design: a malformed draft must still yield a schema-valid row.
    """
    safe = raw if isinstance(raw, dict) else {}

    return OutputRow(
        user_id=_as_text(safe.get("user_id")),
        image_paths=_as_text(safe.get("image_paths")),
        user_claim=_as_text(safe.get("user_claim")),
        claim_object=_as_text(safe.get("claim_object")) or _as_text(claim_object),
        evidence_standard_met=_as_bool(safe.get("evidence_standard_met")),
        evidence_standard_met_reason=_as_text(safe.get("evidence_standard_met_reason")),
        risk_flags=_clamp_risk_flags(safe.get("risk_flags")),
        issue_type=_clamp_enum(
            safe.get("issue_type"), _ISSUE_TYPE_VOCAB, _FALLBACK_ISSUE_TYPE
        ),
        object_part=_clamp_object_part(safe.get("object_part"), claim_object),
        claim_status=_clamp_enum(
            safe.get("claim_status"), _CLAIM_STATUS_VOCAB, _FALLBACK_CLAIM_STATUS
        ),
        claim_status_justification=_as_text(safe.get("claim_status_justification")),
        supporting_image_ids=_clamp_supporting_ids(safe.get("supporting_image_ids")),
        valid_image=_as_bool(safe.get("valid_image")),
        severity=_clamp_enum(safe.get("severity"), _SEVERITY_VOCAB, _FALLBACK_SEVERITY),
    )
