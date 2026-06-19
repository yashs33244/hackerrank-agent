"""Centralized configuration for the Multi-Modal Evidence Review solution.

Single source of truth for filesystem paths, model routing, and runtime tunables.
Every value is overridable through an environment variable so the same code runs
unchanged on a grader's machine, in CI, or locally. Nothing here performs I/O or
spawns a process; importing this module must stay cheap and side-effect free.

No API key is ever read here: inference runs through the installed ``claude`` CLI
under the user's subscription (see AGENTS.md s6 and research/06_self_grill.md D1).
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (resolved from this file, never hardcoded to a user's home directory)
# ---------------------------------------------------------------------------

# code/config.py -> code/ -> repo root.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent

DATASET_DIR: Path = Path(
    os.environ.get("DATASET_DIR", str(REPO_ROOT / "dataset"))
).resolve()

# Image roots. The dataset ships sample and test image trees side by side.
IMAGES_DIR: Path = Path(
    os.environ.get("IMAGES_DIR", str(DATASET_DIR / "images"))
).resolve()
SAMPLE_IMAGES_DIR: Path = IMAGES_DIR / "sample"
TEST_IMAGES_DIR: Path = IMAGES_DIR / "test"

# Disk cache so re-runs and repeated images never re-pay a model call.
CACHE_DIR: Path = Path(
    os.environ.get("CACHE_DIR", str(REPO_ROOT / ".cache"))
).resolve()

# Normalized images (AVIF/WebP converted to PNG) are cached here, mirroring the
# source tree so identical filenames in different cases never collide.
NORMALIZED_DIR: Path = CACHE_DIR / "normalized"

# Dataset CSV files and the output target.
CLAIMS_CSV: Path = DATASET_DIR / "claims.csv"
SAMPLE_CLAIMS_CSV: Path = DATASET_DIR / "sample_claims.csv"
USER_HISTORY_CSV: Path = DATASET_DIR / "user_history.csv"
EVIDENCE_REQUIREMENTS_CSV: Path = DATASET_DIR / "evidence_requirements.csv"
OUTPUT_CSV: Path = Path(
    os.environ.get("OUTPUT_CSV", str(REPO_ROOT / "output.csv"))
).resolve()


# ---------------------------------------------------------------------------
# Model routing (per-stage; see research/07_eng_review.md s1)
# ---------------------------------------------------------------------------

# Bulk per-image perception (S2): cheap, high-volume vision calls.
MODEL_PERCEPTION: str = os.environ.get("MODEL_PERCEPTION", "claude-sonnet-4-6")

# Adjudication (S3) and the ~7 hard rows: the strongest reasoning model.
MODEL_ADJUDICATION: str = os.environ.get("MODEL_ADJUDICATION", "claude-opus-4-8")

# Critic / validator (S5): cheapest model, optional corrective pass.
MODEL_CRITIC: str = os.environ.get("MODEL_CRITIC", "claude-haiku-4-5")

# Claim extraction (S1): one cheap multilingual text call per row.
MODEL_CLAIM_EXTRACT: str = os.environ.get("MODEL_CLAIM_EXTRACT", "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Runtime tunables
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    """Read an integer env var, falling back to ``default`` on absence or
    malformed value. We never crash the whole run on a typo'd override."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean env var (``1/true/yes`` true; ``0/false/no`` false),
    falling back to ``default`` on absence or an unrecognized value."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    token = raw.strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


# Bounded concurrency for the parallel S2 perception subprocesses. Kept modest
# so we stay polite to the subscription usage window.
MAX_CONCURRENCY: int = _env_int("MAX_CONCURRENCY", 6)

# Path to the Claude Code binary. Default assumes it is on PATH.
CLAUDE_BIN: str = os.environ.get("CLAUDE_BIN", "claude")

# Per-call subprocess timeout in seconds. A single headless call (including
# image Reads) must finish within this budget or it is retried.
CLAUDE_TIMEOUT_S: int = _env_int("CLAUDE_TIMEOUT_S", 180)

# Longest edge images are resized to before a vision call. Set to 1568, Claude's
# native vision ceiling (~1.15 MP): the API downscales anything larger, so 1568 is
# the most detail the model can actually use, and going higher only wastes tokens.
# Measured: raising this from 1024 to 1568 lifted object_part 0.85 -> 0.90 (the
# model uses the finer detail to localize the part) with no regression. Pure data
# here; the resize itself lives in images/.
IMAGE_MAX_EDGE: int = _env_int("IMAGE_MAX_EDGE", 1568)

# Independent reads per image, majority-voted (self-consistency). Vision calls are
# not temperature-zero, so >1 denoises the per-image facts and makes the result
# reproducible. Set to 1 to disable voting (cheapest, noisiest).
PERCEPTION_SAMPLES: int = _env_int("PERCEPTION_SAMPLES", 3)

# Multi-model perception ensemble (Karpathy decorrelated voting). Format:
# "model:count,model:count". Perception reads each named model that many times and
# majority-votes across the pooled payloads, so two models' uncorrelated errors
# cancel instead of one model's variance only. Measured (sample): the Sonnet+Opus
# ensemble lifted overall 0.817 -> 0.840 (claim_status 0.80->0.85, issue_type
# 0.70->0.75, severity 0.75->0.80, contradicted-recall 2/5->3/5) over either model
# alone. Set to "" for single-model self-consistency at PERCEPTION_SAMPLES (cheaper,
# faster: drops the Opus reads).
PERCEPTION_ENSEMBLE: str = os.environ.get(
    "PERCEPTION_ENSEMBLE", "claude-sonnet-4-6:2,claude-opus-4-8:2"
)

# Test-time augmentation: also read center + four corner zoom crops of each image
# and pool them. Crops recover small damage the downsized full frame loses (a
# corner dent, a hairline crack). The full image stays authoritative for object /
# quality / authenticity; crops can only RECOVER missed damage (>=2 must agree), so
# this lifts recall without admitting single-crop false positives. Costs 5 extra
# reads per image; off by default.
PERCEPTION_TTA: bool = _env_bool("PERCEPTION_TTA", False)


# Claim-blind perception (S2). When True, the perception model is NOT told what the
# user claimed; it scans the whole object and reports the damage it actually sees.
# Intended to curb the affirmative/visual-dominance bias where a claim-aware model
# confirms the claimed damage even when the image shows something different.
#
# MEASURED (sample, k=3): claim-blind regressed every column (claim_status
# 0.80->0.70, object_part 0.75->0.60, issue_type 0.70->0.55). Without a part
# pointer, the model's part-token disagreements fired false part_mismatch
# contradictions that outnumbered the two sycophancy rows it fixed. So the default
# is claim-AWARE; the flag is retained for reproducibility of that A/B, not for use.
PERCEPTION_CLAIM_BLIND: bool = _env_bool("PERCEPTION_CLAIM_BLIND", False)
