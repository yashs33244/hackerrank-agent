"""Tests for code/io/formatter.py: the single strict CSV write path.

The formatter is the only place a row is serialized, so the contract is pinned
to the byte: 14 columns in OUTPUT_COLUMNS order, every field double-quoted,
lowercase booleans, bare semicolon joins, the literal 'none' for empty
multi-value columns, and UTF-8 with '\n' line endings.
"""

import csv
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "code"))  # for domain.*
sys.path.insert(0, os.path.join(_REPO_ROOT, "code", "io"))  # bare imports

from dataio import formatter  # noqa: E402
from dataio import schema  # noqa: E402
from domain.constants import OUTPUT_COLUMNS  # noqa: E402


def _golden_raw() -> dict:
    return {
        "user_id": "user_005",
        "image_paths": "images/sample/case_005/img_1.jpg",
        "user_claim": "Customer: side mirror is the issue.",
        "claim_object": "car",
        "evidence_standard_met": True,
        "evidence_standard_met_reason": "The side mirror is visible in the image.",
        "risk_flags": ["claim_mismatch", "user_history_risk", "manual_review_required"],
        "issue_type": "scratch",
        "object_part": "side_mirror",
        "claim_status": "contradicted",
        "claim_status_justification": "img_1 shows a scratch, not the claimed break.",
        "supporting_image_ids": ["img_1"],
        "valid_image": True,
        "severity": "low",
    }


def test_to_csv_cells_has_all_14_columns():
    row = schema.coerce_output(_golden_raw(), claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert set(cells.keys()) == set(OUTPUT_COLUMNS)
    assert len(cells) == 14


def test_booleans_serialize_lowercase():
    row = schema.coerce_output(_golden_raw(), claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert cells["evidence_standard_met"] == "true"
    assert cells["valid_image"] == "true"


def test_false_boolean_serializes_lowercase_false():
    raw = _golden_raw()
    raw["valid_image"] = False
    raw["evidence_standard_met"] = False
    row = schema.coerce_output(raw, claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert cells["valid_image"] == "false"
    assert cells["evidence_standard_met"] == "false"


def test_multi_value_joins_with_bare_semicolon_no_spaces():
    row = schema.coerce_output(_golden_raw(), claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert cells["risk_flags"] == "claim_mismatch;user_history_risk;manual_review_required"
    assert " " not in cells["risk_flags"]


def test_empty_risk_flags_emits_none_literal():
    raw = _golden_raw()
    raw["risk_flags"] = []
    row = schema.coerce_output(raw, claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert cells["risk_flags"] == "none"


def test_empty_supporting_ids_emits_none_literal():
    raw = _golden_raw()
    raw["supporting_image_ids"] = []
    raw["claim_status"] = "not_enough_information"
    row = schema.coerce_output(raw, claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert cells["supporting_image_ids"] == "none"


def test_supporting_ids_are_bare_no_extension():
    raw = _golden_raw()
    raw["supporting_image_ids"] = ["img_1.jpg", "img_2.jpg"]
    row = schema.coerce_output(raw, claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert cells["supporting_image_ids"] == "img_1;img_2"


def test_input_columns_echoed_verbatim():
    row = schema.coerce_output(_golden_raw(), claim_object="car")
    cells = formatter.to_csv_cells(row)
    assert cells["user_id"] == "user_005"
    assert cells["image_paths"] == "images/sample/case_005/img_1.jpg"
    assert cells["user_claim"] == "Customer: side mirror is the issue."
    assert cells["claim_object"] == "car"


def test_golden_row_serializes_to_exact_quoted_line(tmp_path):
    row = schema.coerce_output(_golden_raw(), claim_object="car")
    out = tmp_path / "output.csv"
    formatter.write_output_csv([row], str(out))
    raw_bytes = out.read_bytes()
    text = raw_bytes.decode("utf-8")

    expected_header = (
        '"user_id","image_paths","user_claim","claim_object",'
        '"evidence_standard_met","evidence_standard_met_reason","risk_flags",'
        '"issue_type","object_part","claim_status","claim_status_justification",'
        '"supporting_image_ids","valid_image","severity"'
    )
    expected_data = (
        '"user_005","images/sample/case_005/img_1.jpg",'
        '"Customer: side mirror is the issue.","car",'
        '"true","The side mirror is visible in the image.",'
        '"claim_mismatch;user_history_risk;manual_review_required",'
        '"scratch","side_mirror","contradicted",'
        '"img_1 shows a scratch, not the claimed break.",'
        '"img_1","true","low"'
    )
    assert text == expected_header + "\n" + expected_data + "\n"
    # Explicitly assert UTF-8 \n, never \r\n.
    assert b"\r\n" not in raw_bytes


def test_header_equals_output_columns(tmp_path):
    row = schema.coerce_output(_golden_raw(), claim_object="car")
    out = tmp_path / "output.csv"
    formatter.write_output_csv([row], str(out))
    with open(out, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert tuple(header) == OUTPUT_COLUMNS
    assert len(header) == 14


def test_round_trip_header_has_14_columns(tmp_path):
    rows = [
        schema.coerce_output(_golden_raw(), claim_object="car"),
        schema.coerce_output(_golden_raw(), claim_object="car"),
    ]
    out = tmp_path / "output.csv"
    formatter.write_output_csv(rows, str(out))
    with open(out, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert len(reader.fieldnames) == 14
        data_rows = list(reader)
    assert len(data_rows) == 2
    for data in data_rows:
        assert set(data.keys()) == set(OUTPUT_COLUMNS)


def test_field_with_comma_and_quote_stays_quoted_and_escaped(tmp_path):
    raw = _golden_raw()
    raw["user_claim"] = 'He said "hello", then left.'
    row = schema.coerce_output(raw, claim_object="car")
    out = tmp_path / "output.csv"
    formatter.write_output_csv([row], str(out))
    # csv must round-trip the embedded comma and quote without corruption.
    with open(out, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data = next(reader)
    assert data["user_claim"] == 'He said "hello", then left.'
