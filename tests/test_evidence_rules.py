"""Tests for the evidence-requirement loader and claim->rule mapping.

These load the real ``dataset/evidence_requirements.csv`` so the expected
``requirement_id`` strings come from the spec, not from guesses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Put ``code/`` on the path so ``domain`` imports like the rest of the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from domain.evidence_rules import load_rules, rule_for  # noqa: E402
from domain.types import EvidenceRule  # noqa: E402

REQUIREMENTS_CSV = REPO_ROOT / "dataset" / "evidence_requirements.csv"


@pytest.fixture(scope="module")
def rules() -> list[EvidenceRule]:
    return load_rules(REQUIREMENTS_CSV)


def test_load_rules_reads_every_row(rules: list[EvidenceRule]) -> None:
    # The real CSV has 11 requirement rows (header excluded).
    assert len(rules) == 11
    requirement_ids = {rule.requirement_id for rule in rules}
    assert "REQ_GENERAL_OBJECT_PART" in requirement_ids
    assert "REQ_CAR_BODY_PANEL" in requirement_ids
    assert "REQ_PACKAGE_CONTENTS" in requirement_ids


def test_load_rules_returns_typed_rows(rules: list[EvidenceRule]) -> None:
    body_panel = next(r for r in rules if r.requirement_id == "REQ_CAR_BODY_PANEL")
    assert isinstance(body_panel, EvidenceRule)
    assert body_panel.applies_to == "dent or scratch"
    assert body_panel.minimum_image_evidence  # non-empty guidance text


def test_load_rules_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_rules(tmp_path / "does_not_exist.csv")


def test_car_dent_maps_to_body_panel(rules: list[EvidenceRule]) -> None:
    rule = rule_for("car", "a deep dent on the door panel", rules)
    assert rule.requirement_id == "REQ_CAR_BODY_PANEL"


def test_car_scratch_maps_to_body_panel(rules: list[EvidenceRule]) -> None:
    rule = rule_for("car", "long scratch along the fender", rules)
    assert rule.requirement_id == "REQ_CAR_BODY_PANEL"


def test_car_crack_maps_to_glass_light_mirror(rules: list[EvidenceRule]) -> None:
    rule = rule_for("car", "the windshield is cracked", rules)
    assert rule.requirement_id == "REQ_CAR_GLASS_LIGHT_MIRROR"


def test_car_broken_maps_to_glass_light_mirror(rules: list[EvidenceRule]) -> None:
    rule = rule_for("car", "the side mirror is broken off", rules)
    assert rule.requirement_id == "REQ_CAR_GLASS_LIGHT_MIRROR"


def test_car_missing_maps_to_glass_light_mirror(rules: list[EvidenceRule]) -> None:
    rule = rule_for("car", "the headlight is missing", rules)
    assert rule.requirement_id == "REQ_CAR_GLASS_LIGHT_MIRROR"


def test_laptop_screen_maps_to_screen_keyboard_trackpad(
    rules: list[EvidenceRule],
) -> None:
    rule = rule_for("laptop", "cracked laptop screen", rules)
    assert rule.requirement_id == "REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD"


def test_laptop_keyboard_maps_to_screen_keyboard_trackpad(
    rules: list[EvidenceRule],
) -> None:
    rule = rule_for("laptop", "a few keyboard keys are missing", rules)
    assert rule.requirement_id == "REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD"


def test_laptop_hinge_maps_to_body_hinge_port(rules: list[EvidenceRule]) -> None:
    rule = rule_for("laptop", "the hinge is broken", rules)
    assert rule.requirement_id == "REQ_LAPTOP_BODY_HINGE_PORT"


def test_laptop_port_maps_to_body_hinge_port(rules: list[EvidenceRule]) -> None:
    rule = rule_for("laptop", "the usb port is damaged", rules)
    assert rule.requirement_id == "REQ_LAPTOP_BODY_HINGE_PORT"


def test_package_seal_maps_to_exterior(rules: list[EvidenceRule]) -> None:
    rule = rule_for("package", "the seal was torn open", rules)
    assert rule.requirement_id == "REQ_PACKAGE_EXTERIOR"


def test_package_crushed_maps_to_exterior(rules: list[EvidenceRule]) -> None:
    rule = rule_for("package", "the box arrived crushed", rules)
    assert rule.requirement_id == "REQ_PACKAGE_EXTERIOR"


def test_package_water_maps_to_label_or_stain(rules: list[EvidenceRule]) -> None:
    rule = rule_for("package", "water damage soaked the side", rules)
    assert rule.requirement_id == "REQ_PACKAGE_LABEL_OR_STAIN"


def test_package_stain_maps_to_label_or_stain(rules: list[EvidenceRule]) -> None:
    rule = rule_for("package", "a dark stain on the label", rules)
    assert rule.requirement_id == "REQ_PACKAGE_LABEL_OR_STAIN"


def test_package_contents_maps_to_contents(rules: list[EvidenceRule]) -> None:
    rule = rule_for("package", "the contents inside are missing", rules)
    assert rule.requirement_id == "REQ_PACKAGE_CONTENTS"


def test_unknown_object_falls_back_to_general(rules: list[EvidenceRule]) -> None:
    rule = rule_for("toaster", "something is wrong", rules)
    assert rule.requirement_id == "REQ_GENERAL_OBJECT_PART"


def test_unmatched_issue_falls_back_to_general(rules: list[EvidenceRule]) -> None:
    # A car claim with no recognizable issue family still gets a usable rule.
    rule = rule_for("car", "it just feels off somehow", rules)
    assert rule.requirement_id == "REQ_GENERAL_OBJECT_PART"


def test_empty_issue_text_falls_back_to_general(rules: list[EvidenceRule]) -> None:
    rule = rule_for("laptop", "", rules)
    assert rule.requirement_id == "REQ_GENERAL_OBJECT_PART"
