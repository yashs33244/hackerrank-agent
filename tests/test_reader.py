"""Tests for code/io/reader.py: UTF-8, multiline-safe CSV ingestion.

The claim transcripts contain pipes, commas, non-ASCII (Hinglish/Spanish), and
sometimes embedded newlines, so the reader must lean on the csv module rather
than naive splitting. image_paths is split on ';' into a clean list.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "code"))  # for domain.*
sys.path.insert(0, os.path.join(_REPO_ROOT, "code", "io"))  # bare import

from dataio import reader  # noqa: E402
from domain.types import ClaimInput  # noqa: E402


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_read_claims_parses_basic_row(tmp_path):
    text = (
        '"user_id","image_paths","user_claim","claim_object"\n'
        '"user_002","images/test/case_001/img_1.jpg;images/test/case_001/img_2.jpg",'
        '"Customer: front bumper damage.","car"\n'
    )
    path = _write(tmp_path, "claims.csv", text)
    rows = reader.read_claims(path)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, ClaimInput)
    assert row.user_id == "user_002"
    assert row.user_claim == "Customer: front bumper damage."
    assert row.claim_object == "car"


def test_image_paths_split_on_semicolon(tmp_path):
    text = (
        '"user_id","image_paths","user_claim","claim_object"\n'
        '"user_002","a/img_1.jpg;a/img_2.jpg;a/img_3.jpg","claim","car"\n'
    )
    path = _write(tmp_path, "claims.csv", text)
    row = reader.read_claims(path)[0]
    assert row.image_paths == ["a/img_1.jpg", "a/img_2.jpg", "a/img_3.jpg"]
    # raw is preserved verbatim for the echo column.
    assert row.image_paths_raw == "a/img_1.jpg;a/img_2.jpg;a/img_3.jpg"


def test_single_image_path_is_one_element_list(tmp_path):
    text = (
        '"user_id","image_paths","user_claim","claim_object"\n'
        '"user_005","images/test/case_003/img_1.jpg","claim","car"\n'
    )
    path = _write(tmp_path, "claims.csv", text)
    row = reader.read_claims(path)[0]
    assert row.image_paths == ["images/test/case_003/img_1.jpg"]


def test_multiline_field_is_handled(tmp_path):
    # An embedded newline inside a quoted field must not split the row.
    text = (
        '"user_id","image_paths","user_claim","claim_object"\n'
        '"user_009","a/img_1.jpg","line one\nline two","laptop"\n'
    )
    path = _write(tmp_path, "claims.csv", text)
    rows = reader.read_claims(path)
    assert len(rows) == 1
    assert rows[0].user_claim == "line one\nline two"


def test_non_ascii_claim_preserved(tmp_path):
    text = (
        '"user_id","image_paths","user_claim","claim_object"\n'
        '"user_002","a/img_1.jpg","Parking mein car ko scrape lag gaya.","car"\n'
    )
    path = _write(tmp_path, "claims.csv", text)
    row = reader.read_claims(path)[0]
    assert "scrape lag gaya" in row.user_claim


def test_pipes_and_commas_inside_claim_preserved(tmp_path):
    claim = "Customer: hi | Agent: ok, sure | Customer: front bumper, headlight."
    text = (
        '"user_id","image_paths","user_claim","claim_object"\n'
        f'"user_002","a/img_1.jpg","{claim}","car"\n'
    )
    path = _write(tmp_path, "claims.csv", text)
    row = reader.read_claims(path)[0]
    assert row.user_claim == claim


def test_reads_real_claims_csv():
    # Smoke test against the actual dataset to catch schema drift.
    path = os.path.join(_REPO_ROOT, "dataset", "claims.csv")
    rows = reader.read_claims(path)
    assert len(rows) == 44
    first = rows[0]
    assert first.user_id == "user_002"
    assert first.claim_object == "car"
    assert len(first.image_paths) == 3
    # every row must have a non-empty image list and a known object.
    for r in rows:
        assert r.image_paths, f"empty image_paths for {r.user_id}"
        assert r.claim_object in {"car", "laptop", "package"}


def test_read_sample_with_labels_returns_input_and_label_dict():
    path = os.path.join(_REPO_ROOT, "dataset", "sample_claims.csv")
    pairs = reader.read_sample_with_labels(path)
    assert len(pairs) == 20
    claim_input, labels = pairs[0]
    assert isinstance(claim_input, ClaimInput)
    assert claim_input.user_id == "user_001"
    assert claim_input.claim_object == "car"
    # labels carry the 10 produced columns (at minimum these key signals).
    assert labels["claim_status"] == "supported"
    assert labels["issue_type"] == "dent"
    assert labels["object_part"] == "rear_bumper"
    assert labels["severity"] == "medium"
    assert labels["risk_flags"] == "none"
    assert labels["supporting_image_ids"] == "img_1"


def test_read_sample_labels_have_all_ten_produced_columns():
    path = os.path.join(_REPO_ROOT, "dataset", "sample_claims.csv")
    pairs = reader.read_sample_with_labels(path)
    _, labels = pairs[0]
    produced = {
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
    }
    assert produced.issubset(set(labels.keys()))


def test_missing_file_raises_clear_error(tmp_path):
    missing = str(tmp_path / "does_not_exist.csv")
    with pytest.raises(FileNotFoundError):
        reader.read_claims(missing)
