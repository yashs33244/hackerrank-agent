"""Tests for the authenticity-signal helpers.

These signals feed the ``non_original_image`` / ``possible_manipulation`` risk
priors; they never decide ``claim_status``. The tests pin the shape of the
outputs (stable hash, expected dict keys) and a basic near-duplicate detection,
not subjective judgments about any specific dataset image.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Put ``code/`` on the path so ``images`` imports like the rest of the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from images.authenticity import (  # noqa: E402
    exif_signals,
    find_recycled,
    phash_hex,
)

IMAGES_DIR = REPO_ROOT / "dataset" / "images"
KNOWN_JPEG_RELATIVE_PATH = "test/case_030/img_1.jpg"
KNOWN_WEBP_RELATIVE_PATH = "sample/case_001/img_1.jpg"

EXPECTED_EXIF_KEYS = {
    "has_camera_exif",
    "has_editor_software_tag",
    "editor_software",
    "is_screenshot_like",
    "width",
    "height",
}


def test_phash_returns_hex_string() -> None:
    value = phash_hex(IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH)
    assert isinstance(value, str)
    assert len(value) > 0
    # Hex only.
    int(value, 16)


def test_phash_is_stable_for_same_image() -> None:
    path = IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH
    assert phash_hex(path) == phash_hex(path)


def test_phash_differs_for_different_images() -> None:
    a = phash_hex(IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH)
    b = phash_hex(IMAGES_DIR / KNOWN_WEBP_RELATIVE_PATH)
    assert a != b


def test_phash_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        phash_hex(IMAGES_DIR / "missing.jpg")


def test_exif_signals_returns_expected_keys() -> None:
    signals = exif_signals(IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH)
    assert isinstance(signals, dict)
    assert set(signals.keys()) == EXPECTED_EXIF_KEYS


def test_exif_signals_types_are_sane() -> None:
    signals = exif_signals(IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH)
    assert isinstance(signals["has_camera_exif"], bool)
    assert isinstance(signals["has_editor_software_tag"], bool)
    assert isinstance(signals["is_screenshot_like"], bool)
    assert isinstance(signals["width"], int)
    assert isinstance(signals["height"], int)


def test_exif_signals_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        exif_signals(IMAGES_DIR / "missing.jpg")


def test_find_recycled_flags_identical_copies(tmp_path: Path) -> None:
    from PIL import Image

    original = IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH
    copy_path = tmp_path / "copy.png"
    with Image.open(original) as image:
        image.convert("RGB").save(copy_path, format="PNG")

    pairs = find_recycled([original, copy_path])
    assert any(
        {str(original), str(copy_path)} == {str(a), str(b)} for a, b, _ in pairs
    )


def test_find_recycled_ignores_distinct_images() -> None:
    a = IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH
    b = IMAGES_DIR / KNOWN_WEBP_RELATIVE_PATH
    pairs = find_recycled([a, b])
    assert pairs == []


def test_find_recycled_single_image_returns_empty() -> None:
    assert find_recycled([IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH]) == []
