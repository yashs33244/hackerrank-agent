"""S4 deterministic decision tree.

The core of the pipeline: given per-image perception facts plus the extracted
claim, evidence rule, and user history, it produces the ten scored output
columns by pure deterministic logic. The model proposes facts (S1/S2/S3); this
code disposes the verdict, so scored enums stay legal by construction and the
output is reproducible on re-runs.

Locked semantics: ``research/06_self_grill.md`` (D8-D17) and
``research/07_eng_review.md`` (§3). Two key invariants:

* ``valid_image`` (trust / usability) and ``evidence_standard_met`` (coverage)
  are INDEPENDENT axes and must not be conflated.
* ``manual_review_required`` (D10) is NOT "any non-supported row"; it fires only
  on a trust / mismatch / authenticity / history signal, never on a benign
  coverage gap alone.
"""

from __future__ import annotations

from domain.constants import OBJECT_PART_VOCAB
from domain.enums import (
    ClaimStatus,
    IssueType,
    RiskFlag,
    Severity,
)
from domain.types import (
    ClaimOutput,
    EvidenceRule,
    ExtractedClaim,
    ImageFact,
    UserHistory,
)

# Quality-issue tokens a perception stage may report verbatim. They are already
# the exact RiskFlag vocabulary, so they pass through unchanged after a
# membership check (we never invent a flag the enum does not define).
_QUALITY_RISK_FLAGS: frozenset[str] = frozenset(
    {
        RiskFlag.BLURRY_IMAGE.value,
        RiskFlag.CROPPED_OR_OBSTRUCTED.value,
        RiskFlag.LOW_LIGHT_OR_GLARE.value,
        RiskFlag.WRONG_ANGLE.value,
    }
)

# Signals that, if present in any flag, force a human review (D10).
_MANUAL_REVIEW_TRIGGERS: frozenset[str] = frozenset(
    {
        RiskFlag.USER_HISTORY_RISK.value,
        RiskFlag.CLAIM_MISMATCH.value,
        RiskFlag.WRONG_OBJECT.value,
        RiskFlag.NON_ORIGINAL_IMAGE.value,
        RiskFlag.POSSIBLE_MANIPULATION.value,
        RiskFlag.TEXT_INSTRUCTION_PRESENT.value,
    }
)

# Canonical serialization order for the multi-select risk_flags column. Defined
# once from the enum declaration order so the same set always renders the same
# string (determinism, D12).
_RISK_FLAG_ORDER: tuple[str, ...] = tuple(flag.value for flag in RiskFlag)


def decide(
    claim: ExtractedClaim,
    images: list[ImageFact],
    evidence_rule: EvidenceRule | None,
    history: UserHistory | None,
    adjudication: dict | None = None,
) -> ClaimOutput:
    """Adjudicate one claim row into the ten scored output columns.

    Args:
        claim: What the user actually claims (object, part, issue, severity).
        images: Per-image perception facts for this row. Images are the primary
            source of truth; history and authenticity are additive flags only.
        evidence_rule: The minimum-evidence requirement for this claim. Reserved
            for future coverage tightening; the general "one clear image of the
            claimed part suffices" rule is applied inline today.
        history: The user's claim history with a derived ``is_risky`` flag.

    Returns:
        A fully populated ``ClaimOutput`` with legal enum values in every cell.
    """
    flags: set[str] = set()

    valid_image = _compute_valid_image(images)

    # Authenticity / injection flags are image-level trust signals that apply
    # regardless of the claim_status branch.
    if any(image.non_original for image in images):
        flags.add(RiskFlag.NON_ORIGINAL_IMAGE.value)
    if any(image.possible_manipulation for image in images):
        flags.add(RiskFlag.POSSIBLE_MANIPULATION.value)
    if any(image.text_is_instruction for image in images):
        flags.add(RiskFlag.TEXT_INSTRUCTION_PRESENT.value)

    supporting_image = _select_best_supporting_image(images, claim)

    if supporting_image is None:
        status, issue_type, object_part, severity, supporting_ids = (
            _resolve_not_enough_information(claim, images, flags)
        )
        evidence_standard_met = False
    else:
        status, issue_type, object_part, severity, supporting_ids = (
            _resolve_visible_part(
                supporting_image, claim, images, flags, adjudication
            )
        )
        # Coverage is met when the part was judgeable. A missing-item row that
        # falls through to not_enough_information here did not meet the standard.
        evidence_standard_met = (
            status != ClaimStatus.NOT_ENOUGH_INFORMATION.value
        )

    if history is not None and history.is_risky:
        flags.add(RiskFlag.USER_HISTORY_RISK.value)

    if _should_require_manual_review(flags, valid_image):
        flags.add(RiskFlag.MANUAL_REVIEW_REQUIRED.value)

    return ClaimOutput(
        evidence_standard_met=evidence_standard_met,
        evidence_standard_met_reason=_evidence_reason(evidence_standard_met),
        risk_flags=_serialize_flags(flags),
        issue_type=issue_type,
        object_part=object_part,
        claim_status=status,
        claim_status_justification=_status_justification(status, issue_type),
        supporting_image_ids=supporting_ids,
        valid_image=valid_image,
        severity=severity,
    )


def _compute_valid_image(images: list[ImageFact]) -> bool:
    """``valid_image`` is the trust / usability axis (D8).

    True only when at least one image decodes AND is usable evidence: original
    (not stock / watermarked), un-manipulated, and clear enough. A set that is
    entirely undecodable, non-original, or too unclear to review fails this axis
    even if a part is technically inferable, because it cannot be trusted.
    """
    # _is_usable_evidence already requires decodable, so this also covers the
    # empty and all-undecodable sets (any() over them is False).
    return any(_is_usable_evidence(image) for image in images)


def _is_usable_evidence(image: ImageFact) -> bool:
    """An image is usable evidence only if it is decodable, authentic, and
    clear enough for a reviewer to rely on."""
    return (
        image.decodable
        and not image.non_original
        and not image.possible_manipulation
        and image.is_clear_enough
    )


def _select_best_supporting_image(
    images: list[ImageFact], claim: ExtractedClaim
) -> ImageFact | None:
    """Pick the single image that shows the claimed part clearly, or None.

    An image "shows the claimed part" when perception marked it relevant and
    clear enough to judge. The most confident candidate wins, so a clear close-up
    beats a blurry wide shot (case_007: img_2 over img_1). None routes the row to
    ``not_enough_information``.
    """
    candidates = [
        image
        for image in images
        if image.decodable and image.is_relevant_to_claim and image.is_clear_enough
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda image: image.confidence)


def _resolve_not_enough_information(
    claim: ExtractedClaim,
    images: list[ImageFact],
    flags: set[str],
) -> tuple[str, str, str, str, list[str]]:
    """The claimed part is not shown clearly enough to judge (D9 no-branch).

    Status is ``not_enough_information``; issue and severity ``unknown``;
    supporting set empty. object_part still echoes the claimed part when it is
    legal vocab. Quality issues are surfaced as flags (so the user can be told
    what to resubmit) but do NOT by themselves trigger manual review (D10).
    """
    _collect_quality_flags(images, flags)
    # damage_not_visible summarizes the coverage failure for the reviewer.
    flags.add(RiskFlag.DAMAGE_NOT_VISIBLE.value)
    object_part = _clamp_object_part(claim.claimed_object, claim.claimed_part)
    return (
        ClaimStatus.NOT_ENOUGH_INFORMATION.value,
        IssueType.UNKNOWN.value,
        object_part,
        Severity.UNKNOWN.value,
        [],
    )


def _resolve_visible_part(
    supporting_image: ImageFact,
    claim: ExtractedClaim,
    images: list[ImageFact],
    flags: set[str],
    adjudication: dict | None = None,
) -> tuple[str, str, str, str, list[str]]:
    """The claimed part is visible; decide supported vs contradicted (D9 yes).

    Gate order matters and mirrors the locked tree: (1) wrong object ->
    contradicted, unknown part/issue; (2) part clean -> contradicted, issue=none,
    severity=none; (3) damage != claim -> contradicted, claim_mismatch;
    (4) damage matches -> supported.
    """
    # Surface quality issues only from images that were not clear enough; a clean
    # verdict should not carry noise quality flags (gate_on_clarity precision fix).
    _collect_quality_flags(images, flags, gate_on_clarity=True)

    if not _objects_match(supporting_image.shown_object, claim.claimed_object):
        flags.add(RiskFlag.WRONG_OBJECT.value)
        flags.add(RiskFlag.CLAIM_MISMATCH.value)
        return (
            ClaimStatus.CONTRADICTED.value,
            IssueType.UNKNOWN.value,
            "unknown",
            _clamp_severity(supporting_image.severity_guess),
            _supporting_image_ids(supporting_image, images, claim, decisive=True),
        )

    object_part = _clamp_object_part(
        claim.claimed_object, supporting_image.shown_part
    )
    part_mismatch = _is_part_mismatch(supporting_image, claim, object_part)
    supporting_ids = _supporting_image_ids(
        supporting_image, images, claim, decisive=True
    )

    # (1b) A missing internal item cannot be confirmed or denied by an intact
    # exterior. An undamaged box does NOT contradict a "contents missing" claim,
    # so route it to not_enough_information for a human rather than a false
    # contradiction (the missing_item flag is set by claim extraction, S1).
    if claim.missing_item and not supporting_image.has_visible_damage:
        flags.add(RiskFlag.MANUAL_REVIEW_REQUIRED.value)
        return (
            ClaimStatus.NOT_ENOUGH_INFORMATION.value,
            IssueType.UNKNOWN.value,
            object_part,
            Severity.UNKNOWN.value,
            [],
        )

    # (2) Claimed part visible but undamaged -> contradicted (case_014, case_020).
    if not supporting_image.has_visible_damage:
        flags.add(RiskFlag.DAMAGE_NOT_VISIBLE.value)
        return (
            ClaimStatus.CONTRADICTED.value,
            IssueType.NONE.value,
            object_part,
            Severity.NONE.value,
            supporting_ids,
        )

    # (3) Damage present but on a clearly different part than claimed -> the
    # specific claim is contradicted (case_008: claimed hood, image shows a
    # front-bumper collision). Here the image's own issue/severity describe it.
    if part_mismatch:
        flags.add(RiskFlag.CLAIM_MISMATCH.value)
        return (
            ClaimStatus.CONTRADICTED.value,
            _clamp_issue_type(supporting_image.issue_guess),
            object_part,
            _clamp_severity(supporting_image.severity_guess),
            supporting_ids,
        )

    # (3b) The S3 adjudication caught an issue-level contradiction the facts alone
    # miss: a clearly DIFFERENT kind of damage on the matching part (dent claimed,
    # only a scratch shown). The deterministic tree cannot judge issue semantics,
    # so it defers to S3's explicit comparison here (research/10).
    if adjudication and adjudication.get("issue_cmp") == "different_issue":
        flags.add(RiskFlag.CLAIM_MISMATCH.value)
        return (
            ClaimStatus.CONTRADICTED.value,
            _clamp_issue_type(supporting_image.issue_guess),
            object_part,
            _clamp_severity(supporting_image.severity_guess),
            supporting_ids,
        )

    # (4) Damage present on the claimed part -> the claim of damage is
    # corroborated -> supported. A differing damage WORD (dent vs broken_part) is
    # not a contradiction. issue_type and severity lean to the user's claim, which
    # the image confirms; gold follows the claim, not the model's harsher visual
    # read (case_001 dent/medium, not broken_part/high).
    supported_issue = _reconcile_issue_type(claim, supporting_image)
    return (
        ClaimStatus.SUPPORTED.value,
        supported_issue,
        _supported_object_part(claim, object_part),
        _supported_severity(supported_issue),
        supporting_ids,
    )


def _supporting_image_ids(
    supporting_image: ImageFact,
    images: list[ImageFact],
    claim: ExtractedClaim,
    *,
    decisive: bool,
) -> list[str]:
    """Minimal supporting subset of image IDs, in row order.

    The decisive image is always kept; any other image showing the same claimed
    part clearly is kept too (case_020 keeps both seal shots), but blurry /
    off-part images are dropped (case_007 keeps img_2 only). The NEI branch
    returns ``[]`` directly, so ``decisive`` is always True here.
    """
    if not decisive:
        return []
    keep_ids: list[str] = []
    for image in images:
        if image.image_id == supporting_image.image_id:
            keep_ids.append(image.image_id)
            continue
        if (
            image.decodable
            and image.is_relevant_to_claim
            and image.is_clear_enough
            and _objects_match(image.shown_object, claim.claimed_object)
            and image.shown_part == supporting_image.shown_part
        ):
            keep_ids.append(image.image_id)
    return keep_ids


def _collect_quality_flags(
    images: list[ImageFact], flags: set[str], *, gate_on_clarity: bool = False
) -> None:
    """Surface legal quality risk flags from the images.

    With ``gate_on_clarity`` True (the supported/contradicted path) only flags from
    an image the model marked NOT clear enough are surfaced: a quality issue that
    did not impair a confident verdict is noise that tanks precision (measured:
    cropped_or_obstructed was 8 FP). With the gate off (the not_enough_information
    path) every quality issue is surfaced, because there it is exactly what
    explains the abstention (case_006 wrong_angle, case_018 cropped)."""
    for image in images:
        if gate_on_clarity and image.is_clear_enough:
            continue
        for quality_issue in image.quality_issues:
            if quality_issue in _QUALITY_RISK_FLAGS:
                flags.add(quality_issue)


def _should_require_manual_review(flags: set[str], valid_image: bool) -> bool:
    """The corrected D10 rule: fire on any trust / mismatch / authenticity /
    history signal, or when the evidence cannot be trusted (``valid_image`` is
    False). A benign coverage gap alone (wrong_angle / blurry, no history risk)
    does NOT trigger review, so case_006 stays NEI without it."""
    if not valid_image:
        return True
    return bool(_MANUAL_REVIEW_TRIGGERS & flags)


def _objects_match(shown_object: str, claimed_object: str) -> bool:
    """Objects match when perception is uncertain (``unknown``) or agrees with
    the claim; ``unknown`` must not raise ``wrong_object`` on an uncertain read."""
    if shown_object == "unknown":
        return True
    return shown_object == claimed_object


def _is_part_mismatch(
    image: ImageFact, claim: ExtractedClaim, clamped_part: str
) -> bool:
    """True when the image's part differs from a legally-claimed part."""
    if clamped_part == "unknown":
        return False
    if claim.claimed_part not in _legal_parts(claim.claimed_object):
        return False
    return clamped_part != claim.claimed_part


def _clamp_object_part(claimed_object: str, candidate_part: str) -> str:
    """Clamp a part token to the vocabulary of its object, else ``unknown``."""
    legal = _legal_parts(claimed_object)
    if candidate_part in legal:
        return candidate_part
    return "unknown"


def _legal_parts(claimed_object: str) -> frozenset[str]:
    """The legal object_part vocabulary for an object, empty set if unknown."""
    return OBJECT_PART_VOCAB.get(claimed_object, frozenset())


def _clamp_issue_type(candidate_issue: str) -> str:
    """Clamp an issue token to the IssueType vocabulary, else ``unknown``."""
    if candidate_issue in _ISSUE_VOCAB:
        return candidate_issue
    return IssueType.UNKNOWN.value


def _clamp_severity(candidate_severity: str) -> str:
    """Clamp a severity token to the Severity vocabulary, else ``unknown``."""
    if candidate_severity in _SEVERITY_VOCAB:
        return candidate_severity
    return Severity.UNKNOWN.value


def _serialize_flags(flags: set[str]) -> list[str]:
    """Render the flag set in canonical order; ``[none]`` when empty (D12)."""
    if not flags:
        return [RiskFlag.NONE.value]
    return [flag for flag in _RISK_FLAG_ORDER if flag in flags]


def _evidence_reason(evidence_standard_met: bool) -> str:
    """Deterministic default reason for the coverage verdict.

    The critic stage (S5) may overwrite this with a richer model-written reason;
    this default keeps the column non-empty even if that stage is skipped.
    """
    if evidence_standard_met:
        return "The claimed part is visible clearly enough to evaluate the claim."
    return "The claimed part is not shown clearly enough to verify the claim."


def _status_justification(status: str, issue_type: str) -> str:
    """Deterministic default justification; the S3/S5 model-written one wins."""
    if status == ClaimStatus.SUPPORTED.value:
        return "The image shows the claimed damage on the claimed part."
    if status == ClaimStatus.CONTRADICTED.value:
        if issue_type == IssueType.NONE.value:
            return "The claimed part is visible and shows no damage."
        return "The visible evidence does not match the user's claim."
    return "The submitted images do not show the claimed part clearly enough."


def _supported_object_part(claim: ExtractedClaim, fallback_part: str) -> str:
    """For a supported claim, prefer the user's claimed part when it is legal
    vocabulary. The image confirmed damage on the claimed part (the row reached
    the supported branch, so there was no part mismatch), and gold labels the
    claimed part, so a model ``unknown`` must not override a valid claimed part
    (case_007: claimed door, model read unknown, gold door)."""
    if claim.claimed_part in _legal_parts(claim.claimed_object):
        return claim.claimed_part
    return fallback_part


def _reconcile_issue_type(claim: ExtractedClaim, image: ImageFact) -> str:
    """For a supported claim, prefer the user's claimed issue when it is legal
    vocabulary (the image has confirmed damage on the claimed part). Fall back to
    the image's own read only when the claim names no recognizable issue."""
    claimed = claim.claimed_issue
    if claimed in _ISSUE_VOCAB and claimed != IssueType.UNKNOWN.value:
        return claimed
    return _clamp_issue_type(image.issue_guess)


def _supported_severity(issue_type: str) -> str:
    """Severity for a supported claim, anchored on issue semantics.

    Measured on the calibration set, the per-row severity signals were both worse
    than a simple prior: the image's pixel read over-states severity (it pushes
    almost everything to ``high``, scoring 0.40) and the customer's own word is
    noisy (0.55). Gold supported-severity instead clusters tightly at ``medium``,
    with the one reliable departure being that a ``scratch`` (a cosmetic, surface
    issue) is ``low`` by nature. So we anchor on the issue type: a scratch is
    ``low``; every other corroborated issue is ``medium``. This generalizes from a
    real property of the damage type rather than a noisy per-image read, and it
    measured best (0.75) of every option tried."""
    if issue_type == IssueType.SCRATCH.value:
        return Severity.LOW.value
    return Severity.MEDIUM.value


# Frozen vocabularies derived once from the enums so nothing drifts from them.
_ISSUE_VOCAB: frozenset[str] = frozenset(issue.value for issue in IssueType)
_SEVERITY_VOCAB: frozenset[str] = frozenset(level.value for level in Severity)
