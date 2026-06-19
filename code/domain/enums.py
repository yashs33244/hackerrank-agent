"""Closed vocabularies for the evidence-review output schema.

Every value is the exact lowercase token required by ``problem_statement.md``.
A wrong token silently invalidates that output cell, so this module is the
single source of truth for the allowed values and must not be edited without
updating the spec in lock-step.
"""

from enum import StrEnum


class ClaimObject(StrEnum):
    """The three object types a claim can be about."""

    CAR = "car"
    LAPTOP = "laptop"
    PACKAGE = "package"


class ClaimStatus(StrEnum):
    """Final verdict on whether the images back the user's claim."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_ENOUGH_INFORMATION = "not_enough_information"


class IssueType(StrEnum):
    """Visible issue type. ``NONE`` = part visible and undamaged; ``UNKNOWN`` =
    cannot be determined or wrong object."""

    DENT = "dent"
    SCRATCH = "scratch"
    CRACK = "crack"
    GLASS_SHATTER = "glass_shatter"
    BROKEN_PART = "broken_part"
    MISSING_PART = "missing_part"
    TORN_PACKAGING = "torn_packaging"
    CRUSHED_PACKAGING = "crushed_packaging"
    WATER_DAMAGE = "water_damage"
    STAIN = "stain"
    NONE = "none"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Damage severity, calibrated to the pixels, not the customer's words."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class RiskFlag(StrEnum):
    """Quality, mismatch, authenticity, and history risks. Multi-select."""

    NONE = "none"
    BLURRY_IMAGE = "blurry_image"
    CROPPED_OR_OBSTRUCTED = "cropped_or_obstructed"
    LOW_LIGHT_OR_GLARE = "low_light_or_glare"
    WRONG_ANGLE = "wrong_angle"
    WRONG_OBJECT = "wrong_object"
    WRONG_OBJECT_PART = "wrong_object_part"
    DAMAGE_NOT_VISIBLE = "damage_not_visible"
    CLAIM_MISMATCH = "claim_mismatch"
    POSSIBLE_MANIPULATION = "possible_manipulation"
    NON_ORIGINAL_IMAGE = "non_original_image"
    TEXT_INSTRUCTION_PRESENT = "text_instruction_present"
    USER_HISTORY_RISK = "user_history_risk"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class CarPart(StrEnum):
    """Allowed ``object_part`` vocabulary when ``claim_object == car``."""

    FRONT_BUMPER = "front_bumper"
    REAR_BUMPER = "rear_bumper"
    DOOR = "door"
    HOOD = "hood"
    WINDSHIELD = "windshield"
    SIDE_MIRROR = "side_mirror"
    HEADLIGHT = "headlight"
    TAILLIGHT = "taillight"
    FENDER = "fender"
    QUARTER_PANEL = "quarter_panel"
    BODY = "body"
    UNKNOWN = "unknown"


class LaptopPart(StrEnum):
    """Allowed ``object_part`` vocabulary when ``claim_object == laptop``."""

    SCREEN = "screen"
    KEYBOARD = "keyboard"
    TRACKPAD = "trackpad"
    HINGE = "hinge"
    LID = "lid"
    CORNER = "corner"
    PORT = "port"
    BASE = "base"
    BODY = "body"
    UNKNOWN = "unknown"


class PackagePart(StrEnum):
    """Allowed ``object_part`` vocabulary when ``claim_object == package``."""

    BOX = "box"
    PACKAGE_CORNER = "package_corner"
    PACKAGE_SIDE = "package_side"
    SEAL = "seal"
    LABEL = "label"
    CONTENTS = "contents"
    ITEM = "item"
    UNKNOWN = "unknown"
