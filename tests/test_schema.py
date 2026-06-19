"""Tests for code/io/schema.py: the Pydantic OutputRow and coerce_output clamp.

The model's free-text output is never trusted. coerce_output must repair every
illegal value into a legal token without ever raising, so a single bad model
response can never poison the CSV. These tests pin that clamp behaviour.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "code"))  # for domain.*
sys.path.insert(0, os.path.join(_REPO_ROOT, "code", "io"))  # bare schema import

from dataio import schema  # noqa: E402
from domain.constants import INPUT_COLUMNS  # noqa: E402


def _valid_raw() -> dict:
    """A fully legal model draft, used as the baseline each test mutates."""
    return {
        "evidence_standard_met": True,
        "evidence_standard_met_reason": "The screen is visible and the crack verifiable.",
        "risk_flags": ["claim_mismatch"],
        "issue_type": "crack",
        "object_part": "screen",
        "claim_status": "supported",
        "claim_status_justification": "img_1 shows a crack on the laptop screen.",
        "supporting_image_ids": ["img_1"],
        "valid_image": True,
        "severity": "medium",
    }


def test_valid_raw_passes_through_unchanged():
    row = schema.coerce_output(_valid_raw(), claim_object="laptop")
    assert row.claim_status == "supported"
    assert row.issue_type == "crack"
    assert row.object_part == "screen"
    assert row.severity == "medium"
    assert row.risk_flags == ["claim_mismatch"]
    assert row.supporting_image_ids == ["img_1"]
    assert row.evidence_standard_met is True
    assert row.valid_image is True


def test_bogus_object_part_for_laptop_clamps_to_unknown():
    raw = _valid_raw()
    # front_bumper is a car part, illegal for a laptop claim.
    raw["object_part"] = "front_bumper"
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.object_part == "unknown"


def test_object_part_legal_for_object_is_kept():
    raw = _valid_raw()
    raw["object_part"] = "hinge"  # legal laptop part
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.object_part == "hinge"


def test_invalid_risk_flag_is_dropped():
    raw = _valid_raw()
    raw["risk_flags"] = ["claim_mismatch", "totally_made_up_flag"]
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.risk_flags == ["claim_mismatch"]
    assert "totally_made_up_flag" not in row.risk_flags


def test_empty_risk_flags_maps_to_none():
    raw = _valid_raw()
    raw["risk_flags"] = []
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.risk_flags == ["none"]


def test_all_invalid_risk_flags_maps_to_none():
    raw = _valid_raw()
    raw["risk_flags"] = ["nope", "also_nope"]
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.risk_flags == ["none"]


def test_illegal_claim_status_clamps_to_not_enough_information():
    raw = _valid_raw()
    raw["claim_status"] = "maybe_supported"
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.claim_status == "not_enough_information"


def test_illegal_issue_type_clamps_to_unknown():
    raw = _valid_raw()
    raw["issue_type"] = "exploded"
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.issue_type == "unknown"


def test_illegal_severity_clamps_to_unknown():
    raw = _valid_raw()
    raw["severity"] = "catastrophic"
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.severity == "unknown"


def test_missing_fields_do_not_raise_and_get_safe_defaults():
    # A near-empty draft must still produce a legal row, never an exception.
    row = schema.coerce_output({}, claim_object="package")
    assert row.claim_status == "not_enough_information"
    assert row.issue_type == "unknown"
    assert row.severity == "unknown"
    assert row.object_part == "unknown"
    assert row.risk_flags == ["none"]
    assert row.supporting_image_ids == []
    assert row.evidence_standard_met is False
    assert row.valid_image is False


def test_body_part_illegal_for_package_clamps_to_unknown():
    raw = _valid_raw()
    raw["object_part"] = "body"  # body is valid for car/laptop, NOT package
    row = schema.coerce_output(raw, claim_object="package")
    assert row.object_part == "unknown"


def test_string_booleans_are_coerced():
    raw = _valid_raw()
    raw["evidence_standard_met"] = "true"
    raw["valid_image"] = "false"
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.evidence_standard_met is True
    assert row.valid_image is False


def test_supporting_ids_strip_extensions_and_paths():
    raw = _valid_raw()
    raw["supporting_image_ids"] = ["img_1.jpg", "images/test/case_x/img_2.png", "img_3"]
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.supporting_image_ids == ["img_1", "img_2", "img_3"]


def test_risk_flags_deduplicated_and_canonically_ordered():
    raw = _valid_raw()
    # Out of canonical order, with a duplicate.
    raw["risk_flags"] = ["user_history_risk", "claim_mismatch", "claim_mismatch"]
    row = schema.coerce_output(raw, claim_object="laptop")
    # claim_mismatch precedes user_history_risk in the canonical vocab order.
    assert row.risk_flags == ["claim_mismatch", "user_history_risk"]


def test_echoed_input_fields_present_on_model():
    raw = _valid_raw()
    raw["user_id"] = "user_042"
    raw["image_paths"] = "images/test/case_x/img_1.jpg"
    raw["user_claim"] = "screen is cracked"
    raw["claim_object"] = "laptop"
    row = schema.coerce_output(raw, claim_object="laptop")
    for col in INPUT_COLUMNS:
        assert hasattr(row, col)
    assert row.user_id == "user_042"
    assert row.claim_object == "laptop"


def test_none_token_in_risk_flags_with_others_is_dropped():
    raw = _valid_raw()
    # If the model emits 'none' alongside real flags, 'none' is meaningless noise.
    raw["risk_flags"] = ["none", "claim_mismatch"]
    row = schema.coerce_output(raw, claim_object="laptop")
    assert row.risk_flags == ["claim_mismatch"]
