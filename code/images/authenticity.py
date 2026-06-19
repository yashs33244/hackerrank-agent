"""Authenticity signals: EXIF probe, perceptual hash, recycled-image detection.

These helpers produce *priors* that feed the ``non_original_image`` and
``possible_manipulation`` risk flags. They never decide ``claim_status`` on their
own: a stock-looking photo can still truthfully show the claimed damage, so the
adjudicator judges the pixels and treats these only as additive color (spec D8,
D17). Each signal is cheap, deterministic, and has an explicit error path.
"""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import ExifTags, Image, UnidentifiedImageError

# Two perceptual hashes within this Hamming distance are treated as the same
# underlying image (a recycled / re-submitted photo). pHash is 64-bit, so a small
# threshold tolerates re-encoding and resizing without matching unrelated images.
RECYCLED_HAMMING_THRESHOLD = 6

# EXIF tag IDs we read by name via Pillow's reverse lookup. Camera-origin tags
# are the strongest "this came from a real device" signal; their absence is a
# weak prior toward a screenshot, export, or generated image.
_CAMERA_EXIF_TAG_NAMES = ("Make", "Model", "DateTimeOriginal", "LensModel")
_SOFTWARE_TAG_NAME = "Software"

# Editor names that, when present in the Software tag, suggest post-capture
# editing. Matched case-insensitively as substrings.
_EDITOR_SOFTWARE_MARKERS = (
    "photoshop",
    "gimp",
    "lightroom",
    "pixlr",
    "snapseed",
    "paint.net",
    "affinity",
    "canva",
    "facetune",
)

# Screenshots tend to match a phone or desktop panel exactly. We treat an exact
# common-resolution match as a screenshot-like prior. This is intentionally
# conservative: it only fires on exact matches, never on approximate sizes.
_SCREENSHOT_RESOLUTIONS = frozenset(
    {
        (1170, 2532),  # iPhone 12/13/14
        (1284, 2778),  # iPhone Pro Max
        (1125, 2436),  # iPhone X/XS/11 Pro
        (1080, 1920),  # common Android / 1080p portrait
        (1920, 1080),  # 1080p landscape
        (1440, 2560),  # QHD portrait
        (2560, 1440),  # QHD landscape
        (750, 1334),  # iPhone 6/7/8
        (828, 1792),  # iPhone XR/11
    }
)

# Build the name -> tag-id map once so per-image EXIF reads are dict lookups.
_EXIF_NAME_TO_ID = {name: tag_id for tag_id, name in ExifTags.TAGS.items()}


def exif_signals(path: str | Path) -> dict:
    """Return authenticity priors derived from EXIF metadata and dimensions.

    The returned dict always has the same keys so callers can rely on its shape:

        has_camera_exif:        any camera-origin tag (Make/Model/...) is present
        has_editor_software_tag: the Software tag names a known image editor
        editor_software:        the raw Software tag value (empty if absent)
        is_screenshot_like:     dimensions exactly match a common screen panel
        width, height:          decoded pixel dimensions

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        OSError / ValueError: if the bytes cannot be decoded as an image.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"image not found: {file_path}")

    try:
        with Image.open(file_path) as image:
            width, height = image.size
            exif = _read_exif(image)
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise type(error)(f"cannot read EXIF for {file_path}: {error}") from error

    has_camera_exif = any(
        _exif_value(exif, name) for name in _CAMERA_EXIF_TAG_NAMES
    )
    software_value = str(_exif_value(exif, _SOFTWARE_TAG_NAME) or "").strip()
    lowered_software = software_value.lower()
    has_editor_software_tag = any(
        marker in lowered_software for marker in _EDITOR_SOFTWARE_MARKERS
    )
    is_screenshot_like = (width, height) in _SCREENSHOT_RESOLUTIONS

    return {
        "has_camera_exif": bool(has_camera_exif),
        "has_editor_software_tag": bool(has_editor_software_tag),
        "editor_software": software_value,
        "is_screenshot_like": bool(is_screenshot_like),
        "width": int(width),
        "height": int(height),
    }


def phash_hex(path: str | Path) -> str:
    """Return the perceptual hash of the image at ``path`` as a hex string.

    The hash is content-based and stable across re-encoding and resizing, which
    is what makes recycled-image detection possible. Deterministic: the same
    pixels always produce the same hex.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        OSError / ValueError: if the bytes cannot be decoded as an image.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"image not found: {file_path}")
    try:
        with Image.open(file_path) as image:
            # Convert to a consistent mode so palette/alpha variants of the same
            # picture hash identically.
            return str(imagehash.phash(image.convert("RGB")))
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise type(error)(f"cannot hash {file_path}: {error}") from error


def find_recycled(
    paths: list[str | Path],
) -> list[tuple[str, str, int]]:
    """Return near-duplicate image pairs as ``(path_a, path_b, hamming)``.

    A pair is reported when the Hamming distance between its perceptual hashes is
    at most ``RECYCLED_HAMMING_THRESHOLD``, signaling the same image was reused
    or re-submitted. Output is deterministic: pairs are ordered by input index so
    re-runs produce identical lists. Single-image (or empty) input yields ``[]``.

    Unreadable images are skipped rather than aborting the whole comparison, so a
    single bad file cannot hide recycling among the others.
    """
    hashed: list[tuple[str, imagehash.ImageHash]] = []
    for path in paths:
        candidate = Path(path)
        try:
            with Image.open(candidate) as image:
                hashed.append((str(candidate), imagehash.phash(image.convert("RGB"))))
        except (FileNotFoundError, UnidentifiedImageError, OSError, ValueError):
            # A file that will not decode cannot be a recycled match; the
            # decode failure is the normalizer's concern, not this signal's.
            continue

    recycled: list[tuple[str, str, int]] = []
    for left_index in range(len(hashed)):
        for right_index in range(left_index + 1, len(hashed)):
            left_path, left_hash = hashed[left_index]
            right_path, right_hash = hashed[right_index]
            distance = left_hash - right_hash
            if distance <= RECYCLED_HAMMING_THRESHOLD:
                recycled.append((left_path, right_path, int(distance)))
    return recycled


def _read_exif(image: Image.Image) -> dict:
    """Return the image's EXIF mapping, or an empty dict when none is present.

    Pillow raises on a few malformed-EXIF edge cases; those are treated as "no
    usable EXIF" rather than failing the whole probe, because absent metadata is
    itself a valid (weak) authenticity signal.
    """
    try:
        exif = image.getexif()
    except (OSError, ValueError, SyntaxError):
        return {}
    return dict(exif) if exif else {}


def _exif_value(exif: dict, tag_name: str):
    """Look up an EXIF value by human-readable tag name, or return None."""
    tag_id = _EXIF_NAME_TO_ID.get(tag_name)
    if tag_id is None:
        return None
    return exif.get(tag_id)
