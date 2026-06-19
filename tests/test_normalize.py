"""Tests for byte-level format sniffing and image normalization.

These run against the real ``dataset/images`` tree because the whole point of
this module is that the ``.jpg`` extension lies: 8 test files are really AVIF,
many are WebP/PNG. The expected AVIF set is taken from the spec
(``research/06_self_grill.md`` D6), so the assertions check ground truth, not a
guess. Normalization is exercised on a small handful to keep the suite fast.
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

from images.normalize import (  # noqa: E402
    assert_all_decodable,
    normalize_image,
    sniff_format,
)

IMAGES_DIR = REPO_ROOT / "dataset" / "images"

# The 8 test files that are AVIF despite their ``.jpg`` extension (spec D6).
EXPECTED_AVIF_RELATIVE_PATHS = (
    "test/case_001/img_1.jpg",
    "test/case_001/img_3.jpg",
    "test/case_005/img_1.jpg",
    "test/case_005/img_2.jpg",
    "test/case_018/img_1.jpg",
    "test/case_046/img_2.jpg",
    "test/case_047/img_2.jpg",
    "test/case_051/img_1.jpg",
)

# One known sample of each non-AVIF format for the conversion checks.
KNOWN_WEBP_RELATIVE_PATH = "sample/case_001/img_1.jpg"
KNOWN_JPEG_RELATIVE_PATH = "test/case_030/img_1.jpg"


def _all_image_paths() -> list[Path]:
    return sorted(IMAGES_DIR.rglob("*.jpg"))


def test_sniff_finds_exactly_the_expected_avif_files() -> None:
    """Sniffing every image must flag precisely the 8 spec AVIF files."""
    detected_avif = {
        path.relative_to(IMAGES_DIR).as_posix()
        for path in _all_image_paths()
        if sniff_format(path) == "avif"
    }
    # Normalize separators so the comparison holds on any platform.
    expected = {Path(p).as_posix() for p in EXPECTED_AVIF_RELATIVE_PATHS}
    assert detected_avif == expected


def test_sniff_recognizes_webp_and_jpeg() -> None:
    assert sniff_format(IMAGES_DIR / KNOWN_WEBP_RELATIVE_PATH) == "webp"
    assert sniff_format(IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH) == "jpeg"


def test_sniff_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        sniff_format(IMAGES_DIR / "does" / "not" / "exist.jpg")


def test_sniff_unknown_bytes_returns_unknown(tmp_path: Path) -> None:
    junk = tmp_path / "junk.jpg"
    junk.write_bytes(b"not-an-image-at-all-just-text-bytes")
    assert sniff_format(junk) == "unknown"


def test_normalize_avif_produces_decodable_png(tmp_path: Path) -> None:
    from PIL import Image

    source = IMAGES_DIR / EXPECTED_AVIF_RELATIVE_PATHS[0]
    out = normalize_image(source, tmp_path)
    assert out.exists()
    assert out.suffix == ".png"
    with Image.open(out) as decoded:
        decoded.load()
        assert decoded.format == "PNG"


def test_normalize_webp_produces_decodable_png(tmp_path: Path) -> None:
    from PIL import Image

    source = IMAGES_DIR / KNOWN_WEBP_RELATIVE_PATH
    out = normalize_image(source, tmp_path)
    assert out.suffix == ".png"
    with Image.open(out) as decoded:
        decoded.load()
        assert decoded.format == "PNG"


def test_normalize_jpeg_produces_decodable_png(tmp_path: Path) -> None:
    from PIL import Image

    source = IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH
    out = normalize_image(source, tmp_path)
    assert out.suffix == ".png"
    with Image.open(out) as decoded:
        decoded.load()
        assert decoded.format == "PNG"


def test_normalize_resizes_long_edge_to_max(tmp_path: Path) -> None:
    from PIL import Image

    # The known JPEG is wider than 100px, so a small max_edge forces a resize.
    source = IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH
    out = normalize_image(source, tmp_path, max_edge=100)
    with Image.open(out) as decoded:
        assert max(decoded.size) == 100


def test_normalize_does_not_upscale_small_images(tmp_path: Path) -> None:
    from PIL import Image

    source = IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH
    with Image.open(source) as original:
        original_long_edge = max(original.size)
    # A max_edge larger than the image must leave dimensions untouched.
    out = normalize_image(source, tmp_path, max_edge=original_long_edge + 5000)
    with Image.open(out) as decoded:
        assert max(decoded.size) == original_long_edge


def test_normalize_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        normalize_image(IMAGES_DIR / "missing.jpg", tmp_path)


def test_assert_all_decodable_empty_after_normalization(tmp_path: Path) -> None:
    """A normalized sample (one of each tricky format) must all decode."""
    sources = [
        IMAGES_DIR / EXPECTED_AVIF_RELATIVE_PATHS[0],
        IMAGES_DIR / KNOWN_WEBP_RELATIVE_PATH,
        IMAGES_DIR / KNOWN_JPEG_RELATIVE_PATH,
    ]
    normalized = [normalize_image(src, tmp_path) for src in sources]
    assert assert_all_decodable(normalized) == []


def test_assert_all_decodable_reports_broken(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"\x89PNG\r\n\x1a\n-but-truncated-garbage")
    failures = assert_all_decodable([broken])
    assert str(broken) in failures
