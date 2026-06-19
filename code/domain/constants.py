"""Static lookup tables derived from the spec. No behaviour, only data."""

from domain.enums import CarPart, ClaimObject, LaptopPart, PackagePart, RiskFlag

# The 14 output columns, in the exact required order. The formatter is the only
# place allowed to emit a row, and it emits in this order.
OUTPUT_COLUMNS: tuple[str, ...] = (
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
    "evidence_standard_met",
    "evidence_standard_met_reason",
    "risk_flags",
    "issue_type",
    "object_part",
    "claim_status",
    "claim_status_justification",
    "supporting_image_ids",
    "valid_image",
    "severity",
)

# The 4 input columns echoed verbatim into the output.
INPUT_COLUMNS: tuple[str, ...] = ("user_id", "image_paths", "user_claim", "claim_object")

# Allowed object_part tokens per claim_object. Used to clamp model output so a
# laptop never gets a car part. ``unknown`` is the shared fallback.
OBJECT_PART_VOCAB: dict[str, frozenset[str]] = {
    ClaimObject.CAR.value: frozenset(p.value for p in CarPart),
    ClaimObject.LAPTOP.value: frozenset(p.value for p in LaptopPart),
    ClaimObject.PACKAGE.value: frozenset(p.value for p in PackagePart),
}

# Canonical serialization order for the multi-select risk_flags column, so the
# same set always serializes to the same string (determinism).
RISK_FLAG_CANONICAL_ORDER: tuple[str, ...] = tuple(f.value for f in RiskFlag)

# Multi-value columns are joined with a bare semicolon (no surrounding spaces).
MULTI_VALUE_SEPARATOR = ";"

# Literal emitted when a multi-select column is empty.
NONE_TOKEN = "none"
