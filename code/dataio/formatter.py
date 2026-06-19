"""Strict CSV serialization: the single, only write path for output rows.

Every output cell in the project is produced here. Centralizing serialization
makes the byte-level contract (14-column order, double-quoted fields, lowercase
booleans, bare semicolon joins, ``none`` literal, UTF-8 ``\\n``) impossible to
violate elsewhere. Nothing outside this module is permitted to write the CSV.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable

from domain.constants import (
    MULTI_VALUE_SEPARATOR,
    NONE_TOKEN,
    OUTPUT_COLUMNS,
)

from dataio.schema import OutputRow

# Columns that hold a list and serialize to a ';'-joined string or 'none'.
_MULTI_VALUE_COLUMNS: frozenset[str] = frozenset(
    {"risk_flags", "supporting_image_ids"}
)

# Columns that serialize as lowercase 'true'/'false'.
_BOOLEAN_COLUMNS: frozenset[str] = frozenset(
    {"evidence_standard_met", "valid_image"}
)


def _format_boolean(value: bool) -> str:
    """Serialize a bool as the lowercase literal the spec requires."""
    return "true" if value else "false"


def _format_multi_value(values: list[str]) -> str:
    """Join a list with a bare semicolon, or emit the ``none`` literal if empty.

    A trailing or leading separator would silently create an empty token, so the
    join is on a filtered, already-clean list.
    """
    cleaned = [token for token in values if token]
    if not cleaned:
        return NONE_TOKEN
    return MULTI_VALUE_SEPARATOR.join(cleaned)


def to_csv_cells(row: OutputRow) -> dict[str, str]:
    """Render one :class:`OutputRow` into the 14 string cells, keyed by column.

    The returned dict has exactly the keys in ``OUTPUT_COLUMNS``. Booleans are
    lowercased, multi-value columns are ';'-joined (or ``none``), and every other
    field is passed through as text. Quoting is applied later, at write time.
    """
    cells: dict[str, str] = {}
    for column in OUTPUT_COLUMNS:
        value = getattr(row, column)
        if column in _BOOLEAN_COLUMNS:
            cells[column] = _format_boolean(value)
        elif column in _MULTI_VALUE_COLUMNS:
            cells[column] = _format_multi_value(value)
        else:
            cells[column] = "" if value is None else str(value)
    return cells


def write_output_csv(rows: Iterable[OutputRow], path: str) -> None:
    """Write all rows to ``path`` as the strict 14-column output CSV.

    Quotes every field (``QUOTE_ALL``), writes the header in ``OUTPUT_COLUMNS``
    order, uses UTF-8 with ``\\n`` line endings (never ``\\r\\n``), and is the only
    sanctioned CSV writer in the codebase.
    """
    # newline="" lets the csv module control line endings; lineterminator pins
    # them to \n so the file is byte-identical across platforms.
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(OUTPUT_COLUMNS),
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(to_csv_cells(row))
