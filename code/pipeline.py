"""Pipeline orchestration: turn each claim row into one validated ``OutputRow``.

One agent identity, internal stages (research/07_eng_review.md s1):
``S0 normalize`` -> ``S1 claim extract`` -> ``S2 per-image perception`` ->
``S4 deterministic decision tree`` -> ``S6 strict CSV formatter``.

The LLM stages (S1, S2) only propose facts about the images; the deterministic
decision tree (S4) disposes the final scored enums, so every output cell is
grounded in the images and reproducible. Images are the primary source of truth;
user history and authenticity are additive flags that never flip ``claim_status``.
"""

from __future__ import annotations

import concurrent.futures
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

import config
from agent import client as default_client
from agent.claim_extract import extract_claim
from agent.perception import perceive_image
from dataio.formatter import write_output_csv
from dataio.reader import read_claims
from dataio.schema import OutputRow, coerce_output
from domain.decision_tree import decide
from domain.evidence_rules import load_rules, rule_for
from domain.history import load_history
from domain.types import ClaimInput, ImageFact
from images.authenticity import exif_signals
from images.normalize import ImageNormalizationError, normalize_image


def _safe_fallback_row(claim_input: ClaimInput) -> OutputRow:
    """A schema-valid ``not_enough_information`` row, used when a claim cannot be
    processed at all so ``output.csv`` always has exactly one row per input."""
    raw = {
        "user_id": claim_input.user_id,
        "image_paths": claim_input.image_paths_raw,
        "user_claim": claim_input.user_claim,
        "claim_object": claim_input.claim_object,
        "evidence_standard_met": False,
        "evidence_standard_met_reason": (
            "Automated review could not process this claim; routed to manual review."
        ),
        "risk_flags": ["manual_review_required"],
        "issue_type": "unknown",
        "object_part": "unknown",
        "claim_status": "not_enough_information",
        "claim_status_justification": (
            "The system could not evaluate the submitted evidence automatically."
        ),
        "supporting_image_ids": [],
        "valid_image": False,
        "severity": "unknown",
    }
    return coerce_output(raw, claim_input.claim_object)


def _augment_authenticity(fact: ImageFact, source_path: Path) -> None:
    """Layer deterministic EXIF signals on top of the model's visual judgement.
    These only raise trust flags; they never decide ``claim_status``."""
    try:
        signals = exif_signals(source_path)
    except Exception:  # EXIF parsing is best-effort; never fail a row over it.
        return
    # Only a hard editor signature raises the flag. A merely-absent camera EXIF is
    # common for legitimately compressed phone photos, so it must NOT imply
    # non-original (that produced false positives on real claims). Visual
    # watermark/screenshot detection is left to the perception model.
    if signals.get("has_editor_software_tag"):
        fact.non_original = True


def _perceive_row_images(
    claim_input: ClaimInput,
    claim: Any,
    image_root: Path,
    client: Any,
    normalized_dir: Path,
) -> list[ImageFact]:
    """S0 + S2: normalize then perceive each image in the row."""
    facts: list[ImageFact] = []
    for relative_path in claim_input.image_paths:
        image_id = claim_input.image_id_for(relative_path)
        source_path = Path(image_root) / relative_path
        # Mirror the source tree so identical filenames (img_1) never collide.
        target_dir = normalized_dir / Path(relative_path).parent
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            usable_path = normalize_image(
                source_path, target_dir, max_edge=config.IMAGE_MAX_EDGE
            )
        except (ImageNormalizationError, FileNotFoundError, OSError):
            usable_path = source_path  # fall back to original; Read may still cope
        fact = perceive_image(
            str(usable_path), image_id, claim, client, samples=config.PERCEPTION_SAMPLES
        )
        fact.path = str(source_path)
        _augment_authenticity(fact, source_path)
        facts.append(fact)
    return facts


def process_claim(
    claim_input: ClaimInput,
    history_map: dict,
    rules: list,
    image_root: Path,
    client: Any = default_client,
    normalized_dir: Path | None = None,
) -> OutputRow:
    """Run one claim row through S1 -> S2 -> S4 and return a validated row."""
    normalized_dir = normalized_dir or config.NORMALIZED_DIR
    claim = extract_claim(claim_input.user_claim, claim_input.claim_object, client)
    images = _perceive_row_images(
        claim_input, claim, image_root, client, normalized_dir
    )
    rule = rule_for(
        claim_input.claim_object, claim.claimed_issue or claim.claimed_part, rules
    )
    history = history_map.get(claim_input.user_id)
    # NOTE: the S3 per-attribute adjudication (agent.adjudicate.compare_attributes)
    # is implemented and the decision tree accepts it, but it is intentionally NOT
    # wired here: measured on the sample it did not improve contradicted-recall
    # (our perception is claim-aware, so S3 inherits the same bias the research
    # design assumed claim-blind facts would avoid). Kept as documented future work.
    output = decide(claim, images, rule, history)
    raw = {
        "user_id": claim_input.user_id,
        "image_paths": claim_input.image_paths_raw,
        "user_claim": claim_input.user_claim,
        "claim_object": claim_input.claim_object,
        **asdict(output),
    }
    return coerce_output(raw, claim_input.claim_object)


def run(
    claims_path: str,
    output_path: str,
    image_root: Path,
    *,
    limit: int | None = None,
    max_workers: int | None = None,
    client: Any = default_client,
) -> list[OutputRow]:
    """Process every row of ``claims_path`` and write ``output_path``.

    Rows run concurrently (bounded by ``max_workers``) because each row is I/O
    bound on headless ``claude`` subprocess calls. A row that raises is replaced
    by a safe fallback so the output always has one row per input.
    """
    rows = read_claims(str(claims_path))
    if limit is not None:
        rows = rows[:limit]
    history_map = load_history(str(config.USER_HISTORY_CSV))
    rules = load_rules(str(config.EVIDENCE_REQUIREMENTS_CSV))
    workers = max_workers or config.MAX_CONCURRENCY

    def _work(claim_input: ClaimInput) -> OutputRow:
        try:
            return process_claim(claim_input, history_map, rules, image_root, client)
        except Exception:  # one bad row must never sink the whole batch.
            traceback.print_exc()
            return _safe_fallback_row(claim_input)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_work, rows))

    write_output_csv(results, str(output_path))
    return results
