"""Byte-sniff the true image format and normalize anything to a decodable PNG.

The dataset stores every image with a ``.jpg`` extension regardless of its real
encoding: 67 are JPEG, 19 PNG, 17 WebP, and 8 are AVIF. A naive loader that
trusts the extension corrupts those rows silently, so this module identifies the
real format from the leading bytes and converts everything to a resized PNG that
every downstream stage can decode.

AVIF is handled by Pillow when its AVIF plugin is present, and otherwise falls
back to ImageMagick (``magick`` / ``convert``) because ``pillow_heif`` is not an
installed dependency. Every external operation (filesystem, decode, subprocess)
has an explicit error path; nothing is swallowed silently.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# Long-edge target in pixels. Resizing before any vision call cuts token cost by
# roughly half while keeping damage detail legible. Overridable per call so the
# centralized pipeline config (code/config.py) stays the single source of truth.
DEFAULT_MAX_EDGE = 1024

# Seconds before an ImageMagick conversion is considered hung and aborted.
MAGICK_TIMEOUT_SECONDS = 30

# Format tokens this module emits. ``unknown`` means the bytes matched no known
# signature; the caller decides how to treat it (it is not silently dropped).
FORMAT_JPEG = "jpeg"
FORMAT_PNG = "png"
FORMAT_WEBP = "webp"
FORMAT_AVIF = "avif"
FORMAT_UNKNOWN = "unknown"

# Number of leading bytes needed to disambiguate every supported signature. The
# ISOBMFF brand for AVIF sits at offset 8, so 16 bytes is always sufficient.
_SNIFF_BYTE_COUNT = 16

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_RIFF_MAGIC = b"RIFF"
_WEBP_BRAND = b"WEBP"
_FTYP_MARKER = b"ftyp"
_AVIF_BRANDS = (b"avif", b"avis")


class ImageNormalizationError(RuntimeError):
    """Raised when an image cannot be decoded or converted by any backend."""


def sniff_format(path: str | Path) -> str:
    """Return the true image format of ``path`` from its leading bytes.

    The file extension is ignored on purpose. Returns one of ``jpeg``, ``png``,
    ``webp``, ``avif``, or ``unknown``.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        OSError: if the file exists but cannot be read.
    """
    file_path = Path(path)
    # Opening explicitly surfaces a FileNotFoundError instead of returning a
    # misleading "unknown" for a path that simply is not there.
    with file_path.open("rb") as handle:
        header = handle.read(_SNIFF_BYTE_COUNT)

    if header.startswith(_JPEG_MAGIC):
        return FORMAT_JPEG
    if header.startswith(_PNG_MAGIC):
        return FORMAT_PNG
    if header.startswith(_RIFF_MAGIC) and header[8:12] == _WEBP_BRAND:
        return FORMAT_WEBP
    if _FTYP_MARKER in header[4:12] and header[8:12] in _AVIF_BRANDS:
        return FORMAT_AVIF
    return FORMAT_UNKNOWN


def normalize_image(
    src_path: str | Path,
    out_dir: str | Path,
    max_edge: int = DEFAULT_MAX_EDGE,
) -> Path:
    """Convert any supported image to a resized PNG in ``out_dir``.

    The output is named ``<stem>.png`` (the original stem, so ``img_2.jpg`` ->
    ``img_2.png``) and its long edge is at most ``max_edge`` pixels. Smaller
    images are never upscaled. AVIF is decoded by Pillow when available and by
    ImageMagick otherwise.

    Returns:
        Path to the written PNG.

    Raises:
        FileNotFoundError: if ``src_path`` does not exist.
        ValueError: if ``max_edge`` is not positive.
        ImageNormalizationError: if no backend can decode the source.
    """
    source = Path(src_path)
    if not source.exists():
        raise FileNotFoundError(f"source image not found: {source}")
    if max_edge <= 0:
        raise ValueError(f"max_edge must be positive, got {max_edge}")

    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{source.stem}.png"

    image = _decode_to_pillow(source)
    try:
        resized = _resize_long_edge(image, max_edge)
        # PNG has no alpha requirement here, but preserving RGBA when present
        # avoids destroying transparency in the rare PNG/WebP that uses it.
        if resized.mode not in ("RGB", "RGBA"):
            resized = resized.convert("RGB")
        resized.save(destination, format="PNG")
    finally:
        image.close()

    return destination


def assert_all_decodable(paths: list[str | Path]) -> list[str]:
    """Return the string paths in ``paths`` that fail to fully decode.

    Used as the pre-run gate that proves every normalized image is loadable
    before a single model call is spent. An empty list means all are good.
    Pillow's lazy loading is forced with ``load()`` so truncated files are
    caught here rather than mid-pipeline.
    """
    failures: list[str] = []
    for path in paths:
        candidate = Path(path)
        try:
            with Image.open(candidate) as image:
                image.load()
        except (FileNotFoundError, UnidentifiedImageError, OSError, ValueError):
            failures.append(str(candidate))
    return failures


def _decode_to_pillow(source: Path) -> Image.Image:
    """Open ``source`` as a Pillow image, falling back to ImageMagick for AVIF.

    Pillow is tried first for every format because it is fast and dependency-free
    here. If it cannot decode the bytes (typically AVIF on installs without the
    plugin), ImageMagick converts the file to a temporary PNG that Pillow can
    then load. Raises ImageNormalizationError if both backends fail.
    """
    try:
        image = Image.open(source)
        image.load()
        return image
    except (UnidentifiedImageError, OSError, ValueError) as pillow_error:
        # Pillow could not handle the bytes. Try ImageMagick before giving up.
        try:
            return _decode_via_imagemagick(source)
        except ImageNormalizationError as magick_error:
            raise ImageNormalizationError(
                f"no backend could decode {source}: "
                f"pillow={pillow_error!r}; imagemagick={magick_error!r}"
            ) from magick_error


def _decode_via_imagemagick(source: Path) -> Image.Image:
    """Convert ``source`` to PNG via ImageMagick and load it with Pillow.

    Prefers the modern ``magick`` binary and falls back to legacy ``convert``.
    Raises ImageNormalizationError if neither binary exists or the conversion
    fails (nonzero exit / timeout / unreadable output).
    """
    binary = shutil.which("magick") or shutil.which("convert")
    if binary is None:
        raise ImageNormalizationError(
            "ImageMagick not found (need 'magick' or 'convert' on PATH) to "
            f"decode {source}"
        )

    # A temp PNG is the handoff between ImageMagick and Pillow. It is read back
    # into memory immediately, so it can be deleted right after.
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        temp_png = Path(temp_file.name)
    try:
        command = [binary, str(source), str(temp_png)]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=MAGICK_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as timeout_error:
            raise ImageNormalizationError(
                f"ImageMagick timed out converting {source}"
            ) from timeout_error
        except OSError as os_error:
            raise ImageNormalizationError(
                f"failed to launch ImageMagick for {source}: {os_error}"
            ) from os_error

        if result.returncode != 0:
            raise ImageNormalizationError(
                f"ImageMagick failed on {source} (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        try:
            converted = Image.open(temp_png)
            converted.load()
        except (UnidentifiedImageError, OSError, ValueError) as load_error:
            raise ImageNormalizationError(
                f"ImageMagick output for {source} was not decodable: {load_error}"
            ) from load_error
        # Detach from the temp file so it can be deleted while the image lives on.
        return converted.copy()
    finally:
        temp_png.unlink(missing_ok=True)


def _resize_long_edge(image: Image.Image, max_edge: int) -> Image.Image:
    """Downscale ``image`` so its longest side is ``max_edge``; never upscale.

    Returns the original image untouched when it already fits, so small images
    are not blurred by needless interpolation.
    """
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image
    scale = max_edge / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)
