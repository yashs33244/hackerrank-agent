"""Evidence-requirement loader and claim-to-rule mapping.

``evidence_requirements.csv`` lists the minimum image evidence a claim must
satisfy before a verdict can be defended. Each row is keyed by a
``requirement_id`` and scoped by ``claim_object`` + an ``applies_to`` issue
family. This module loads those rows and maps a single claim (object +
free-text issue description) to the single best-matching requirement, falling
back to ``REQ_GENERAL_OBJECT_PART`` when nothing more specific applies.

WHY a keyword map and not the model: the requirement that governs a claim is a
deterministic property of (object, issue family). Deriving it in pure Python
keeps it auditable and removes one source of LLM nondeterminism from the
evidence-sufficiency gate (S4).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from domain.types import EvidenceRule

# Fallback requirement when no object/issue-specific rule matches. It exists in
# the CSV and is the most permissive "show the object and part" requirement.
GENERAL_REQUIREMENT_ID = "REQ_GENERAL_OBJECT_PART"

# Issue-family keyword tables, per object. Order matters: the first family whose
# keyword appears in the issue text wins, so more-specific families are checked
# before broader ones. Keywords are matched as case-insensitive substrings of
# the (object + issue) text, which is why short tokens like "lid" are avoided in
# favour of unambiguous ones.
#
# Each entry maps a target ``requirement_id`` to the keywords that select it.
_CAR_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # crack / broken / missing -> glass, light, mirror, component
    (
        "REQ_CAR_GLASS_LIGHT_MIRROR",
        ("crack", "shatter", "broken", "broke", "missing", "smash"),
    ),
    # dent / scratch -> body panel
    ("REQ_CAR_BODY_PANEL", ("dent", "scratch", "scrape", "scuff", "ding")),
)

_LAPTOP_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # hinge / lid / corner / body / base / port -> body/hinge/port requirement.
    # Checked before the screen/keyboard family because some of these parts can
    # co-occur with surface-damage words.
    (
        "REQ_LAPTOP_BODY_HINGE_PORT",
        ("hinge", "lid", "corner", "port", "base", "body", "chassis", "casing"),
    ),
    # screen / keyboard / trackpad -> surface-damage requirement
    (
        "REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD",
        ("screen", "display", "keyboard", "key", "trackpad", "touchpad"),
    ),
)

_PACKAGE_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # water / stain / label -> label or stain requirement (checked first so a
    # "water-stained label" does not fall into the exterior family).
    (
        "REQ_PACKAGE_LABEL_OR_STAIN",
        ("water", "stain", "wet", "soak", "damp", "label"),
    ),
    # crushed / torn / seal -> exterior requirement
    (
        "REQ_PACKAGE_EXTERIOR",
        ("crush", "torn", "tear", "seal", "dent", "smash", "open"),
    ),
    # contents / inner item -> contents requirement
    (
        "REQ_PACKAGE_CONTENTS",
        ("content", "inside", "inner", "item", "missing", "damaged item"),
    ),
)

# Object -> ordered family table.
_FAMILIES_BY_OBJECT: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "car": _CAR_FAMILIES,
    "laptop": _LAPTOP_FAMILIES,
    "package": _PACKAGE_FAMILIES,
}


def load_rules(path: str | Path) -> list[EvidenceRule]:
    """Load every requirement row from ``evidence_requirements.csv``.

    Args:
        path: Filesystem path to the requirements CSV.

    Returns:
        One ``EvidenceRule`` per data row, preserving file order.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If a required column is missing from the header.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"evidence requirements CSV not found: {csv_path}")

    rules: list[EvidenceRule] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _assert_columns(
            reader.fieldnames,
            {"requirement_id", "applies_to", "minimum_image_evidence"},
            csv_path,
        )
        for row in reader:
            rules.append(
                EvidenceRule(
                    requirement_id=row["requirement_id"].strip(),
                    applies_to=row["applies_to"].strip(),
                    minimum_image_evidence=row["minimum_image_evidence"].strip(),
                )
            )
    return rules


def rule_for(
    claim_object: str,
    issue_or_family: str,
    rules: list[EvidenceRule],
) -> EvidenceRule:
    """Pick the single requirement that governs this claim.

    The match is decided by ``claim_object`` plus the issue family inferred from
    ``issue_or_family`` (a free-text issue description or family keyword). If no
    object-specific family matches, the general requirement is returned so the
    caller always gets a usable rule.

    Args:
        claim_object: The claim object token (``car`` | ``laptop`` | ``package``
            or any other string, which falls back to the general rule).
        issue_or_family: Free text describing the claimed issue. May be empty.
        rules: The list returned by :func:`load_rules`.

    Returns:
        The best-matching ``EvidenceRule``; never ``None``.

    Raises:
        ValueError: If neither the matched requirement nor the general fallback
            is present in ``rules`` (an inconsistent CSV).
    """
    by_id = {rule.requirement_id: rule for rule in rules}
    requirement_id = _requirement_id_for(claim_object, issue_or_family)

    rule = by_id.get(requirement_id)
    if rule is not None:
        return rule

    fallback = by_id.get(GENERAL_REQUIREMENT_ID)
    if fallback is None:
        raise ValueError(
            "evidence requirements are missing both the matched rule "
            f"'{requirement_id}' and the fallback '{GENERAL_REQUIREMENT_ID}'"
        )
    return fallback


def _requirement_id_for(claim_object: str, issue_or_family: str) -> str:
    """Resolve the requirement id from object + issue text (no CSV lookup)."""
    families = _FAMILIES_BY_OBJECT.get((claim_object or "").strip().lower())
    if families is None:
        return GENERAL_REQUIREMENT_ID

    haystack = f"{claim_object} {issue_or_family}".lower()
    for requirement_id, keywords in families:
        if any(_keyword_matches(keyword, haystack) for keyword in keywords):
            return requirement_id
    return GENERAL_REQUIREMENT_ID


def _keyword_matches(keyword: str, haystack: str) -> bool:
    """Whole-word (stem) match of ``keyword`` against ``haystack``.

    WHY not a plain substring: a transcript carries words like "support" that
    embed shorter keywords such as "port". A word-boundary stem match treats
    "port" as the start of a word, so it matches "port" / "ports" but never the
    "port" inside "support" - removing those false positives while still letting
    stems like "crush" match "crushed" and "broke" match "broken".
    """
    pattern = rf"\b{re.escape(keyword)}\w*"
    return re.search(pattern, haystack) is not None


def _assert_columns(
    fieldnames: list[str] | None,
    required: set[str],
    csv_path: Path,
) -> None:
    """Fail loudly if the CSV header is missing a column we depend on."""
    present = set(fieldnames or ())
    missing = required - present
    if missing:
        raise ValueError(
            f"{csv_path} is missing required column(s): {sorted(missing)}"
        )
