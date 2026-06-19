"""Typed state objects that flow through the pipeline.

One ``ClaimState`` is built per input row. Each stage reads only the fields it
needs and writes only its own, so context stays scoped and the data flow is
auditable (mirrors the prior solution's typed-state spine).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClaimInput:
    """A raw row from ``claims.csv`` / ``sample_claims.csv``."""

    user_id: str
    image_paths_raw: str  # original semicolon-joined string, echoed verbatim
    user_claim: str
    claim_object: str
    image_paths: list[str] = field(default_factory=list)  # split, relative paths

    def image_id_for(self, path: str) -> str:
        """Image ID = filename without extension (e.g. ``img_2``)."""
        name = path.rsplit("/", 1)[-1]
        return name.rsplit(".", 1)[0]


@dataclass
class UserHistory:
    """A row from ``user_history.csv`` plus a derived risk flag."""

    user_id: str
    past_claim_count: int
    accept_claim: int
    manual_review_claim: int
    rejected_claim: int
    last_90_days_claim_count: int
    history_flags: list[str]
    history_summary: str
    is_risky: bool  # derived: history_flags signals risk -> user_history_risk


@dataclass
class ExtractedClaim:
    """What the user actually claims, parsed from the (possibly multilingual)
    conversation."""

    claimed_object: str
    claimed_part: str
    claimed_issue: str
    claimed_severity_word: str
    missing_item: bool = False
    secondary_parts: list[str] = field(default_factory=list)
    language: str = "en"


@dataclass
class ImageFact:
    """Per-image perception result. The images are the primary source of truth,
    so every downstream decision is grounded in these facts."""

    image_id: str
    path: str
    image_format: str  # real format from byte-sniff (jpeg/png/webp/avif)
    decodable: bool = True
    shown_object: str = "unknown"
    shown_part: str = "unknown"
    has_visible_damage: bool = False
    issue_guess: str = "unknown"
    severity_guess: str = "unknown"
    quality_issues: list[str] = field(default_factory=list)
    embedded_text: str = ""
    text_is_instruction: bool = False
    authenticity_notes: str = ""
    non_original: bool = False
    possible_manipulation: bool = False
    is_relevant_to_claim: bool = False
    is_clear_enough: bool = False
    confidence: float = 0.0


@dataclass
class EvidenceRule:
    """The minimum-evidence requirement that applies to this claim."""

    requirement_id: str
    applies_to: str
    minimum_image_evidence: str


@dataclass
class ClaimOutput:
    """The 10 produced columns (inputs are echoed separately)."""

    evidence_standard_met: bool
    evidence_standard_met_reason: str
    risk_flags: list[str]
    issue_type: str
    object_part: str
    claim_status: str
    claim_status_justification: str
    supporting_image_ids: list[str]
    valid_image: bool
    severity: str


@dataclass
class ClaimState:
    """The full per-row state carried through stages S0..S6."""

    claim_input: ClaimInput
    history: UserHistory | None = None
    evidence_rule: EvidenceRule | None = None
    claim: ExtractedClaim | None = None
    images: list[ImageFact] = field(default_factory=list)
    output: ClaimOutput | None = None
