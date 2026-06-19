"""CSV ingestion for claims and labelled samples.

Claim transcripts contain pipes, commas, non-ASCII (Hinglish/Spanish/Pinyin),
and occasionally embedded newlines, so parsing goes through the ``csv`` module
(which is quote- and multiline-aware) rather than any naive line splitting. The
only structured transform is splitting ``image_paths`` on ``;`` into a list.
"""

from __future__ import annotations

import csv

from domain.constants import INPUT_COLUMNS
from domain.types import ClaimInput

# The produced columns present in a labelled sample file, beyond the 4 inputs.
_LABEL_COLUMNS: tuple[str, ...] = (
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

# Separator for the ``image_paths`` column. Matches the formatter's join token,
# but kept local because this is the *input* contract, not the output one.
_IMAGE_PATH_SEPARATOR = ";"


def _split_image_paths(raw: str) -> list[str]:
    """Split a semicolon-joined ``image_paths`` cell into clean relative paths.

    Empty segments (from a stray trailing ``;``) are dropped so downstream image
    loading never receives a blank path.
    """
    return [segment.strip() for segment in raw.split(_IMAGE_PATH_SEPARATOR) if segment.strip()]


def _to_claim_input(record: dict[str, str]) -> ClaimInput:
    """Build a :class:`ClaimInput` from one parsed CSV record.

    ``image_paths_raw`` keeps the original cell verbatim because it is echoed
    unchanged into the output; ``image_paths`` is the split working list.
    """
    image_paths_raw = record.get("image_paths", "") or ""
    return ClaimInput(
        user_id=record.get("user_id", "") or "",
        image_paths_raw=image_paths_raw,
        user_claim=record.get("user_claim", "") or "",
        claim_object=record.get("claim_object", "") or "",
        image_paths=_split_image_paths(image_paths_raw),
    )


def _read_records(path: str) -> list[dict[str, str]]:
    """Read a CSV into a list of dict records, UTF-8 and multiline-safe.

    Surfaces a clear ``FileNotFoundError`` rather than failing obscurely later;
    the caller (pipeline) decides how to handle a missing dataset file.
    """
    try:
        # newline="" is required so the csv module, not the OS, interprets
        # newlines inside quoted fields.
        with open(path, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError:
        raise FileNotFoundError(f"claims CSV not found: {path}") from None


def read_claims(path: str) -> list[ClaimInput]:
    """Read ``claims.csv`` (or any file with the 4 input columns) into rows.

    Returns one :class:`ClaimInput` per data row, with ``image_paths`` already
    split on ``;``.
    """
    return [_to_claim_input(record) for record in _read_records(path)]


def read_sample_with_labels(path: str) -> list[tuple[ClaimInput, dict[str, str]]]:
    """Read ``sample_claims.csv`` into (input, labels) pairs for evaluation.

    The input half is the same :class:`ClaimInput` the pipeline consumes; the
    labels half is the 10 produced columns as raw strings, used purely as a
    calibration/scoring signal (never to hardcode the pipeline).
    """
    pairs: list[tuple[ClaimInput, dict[str, str]]] = []
    for record in _read_records(path):
        claim_input = _to_claim_input(record)
        labels = {column: (record.get(column, "") or "") for column in _LABEL_COLUMNS}
        pairs.append((claim_input, labels))
    return pairs


# Exposed so callers can assert a file has the expected input header without
# re-deriving the column list here.
EXPECTED_INPUT_COLUMNS: tuple[str, ...] = INPUT_COLUMNS
