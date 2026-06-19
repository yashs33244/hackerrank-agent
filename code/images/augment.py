"""Test-time augmentation: produce zoom crops of one image for multi-view reading.

A downsized full photo loses small damage (a hairline crack, a corner dent). The
classic vision fix is test-time augmentation - read several zoomed views and pool
the findings, so detail that is invisible at full-frame becomes legible in a crop.
We emit a center crop plus the four corner crops (overlapping), each upscaled back
to the model's resolution, because claim damage can sit anywhere in frame (a
corner dent would be missed by a center crop alone).

Crops are written next to the normalized image and content-stable (same input ->
same crops), so the perception cache still pins results across re-runs.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# Each crop covers this fraction of the full width/height. 0.65 with center + four
# corners tiles the whole frame with overlap, so no region is unobserved while each
# crop is a ~1.5x zoom that surfaces small damage.
_CROP_FRACTION = 0.65

# Anchor positions as (left_fraction, top_fraction) of the crop's top-left corner.
_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.5 - _CROP_FRACTION / 2, 0.5 - _CROP_FRACTION / 2),  # center
    (0.0, 0.0),  # top-left
    (1.0 - _CROP_FRACTION, 0.0),  # top-right
    (0.0, 1.0 - _CROP_FRACTION),  # bottom-left
    (1.0 - _CROP_FRACTION, 1.0 - _CROP_FRACTION),  # bottom-right
)

_CROP_NAMES: tuple[str, ...] = ("center", "tl", "tr", "bl", "br")


def tile_crops(image_path: str | Path, out_dir: str | Path, max_edge: int) -> list[Path]:
    """Write center + four corner zoom crops of ``image_path`` into ``out_dir``.

    Each crop is ``_CROP_FRACTION`` of the frame, upscaled so its long edge is
    ``max_edge`` (the model sees it at full resolution). Returns the crop paths in
    a stable order; on any decode error returns an empty list so the caller simply
    falls back to the full-image read.
    """
    source = Path(image_path)
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as image:
            image.load()
            rgb = image.convert("RGB")
    except (OSError, ValueError):
        return []

    width, height = rgb.size
    crop_width = max(1, int(width * _CROP_FRACTION))
    crop_height = max(1, int(height * _CROP_FRACTION))
    crops: list[Path] = []
    for name, (left_fraction, top_fraction) in zip(_CROP_NAMES, _ANCHORS):
        left = max(0, min(width - crop_width, int(width * left_fraction)))
        top = max(0, min(height - crop_height, int(height * top_fraction)))
        tile = rgb.crop((left, top, left + crop_width, top + crop_height))
        tile = _upscale_long_edge(tile, max_edge)
        destination = output_dir / f"{source.stem}__crop_{name}.png"
        try:
            tile.save(destination, format="PNG")
        except OSError:
            continue
        crops.append(destination)
    return crops


def _upscale_long_edge(image: Image.Image, max_edge: int) -> Image.Image:
    """Scale ``image`` so its long edge is ``max_edge`` (zoom in on the crop)."""
    width, height = image.size
    longest = max(width, height)
    if longest == max_edge or longest == 0:
        return image
    scale = max_edge / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)
