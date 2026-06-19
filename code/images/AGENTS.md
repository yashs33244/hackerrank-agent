# code/images/ — AGENTS.md

Image handling. The extension lies: `.jpg` files are really JPEG/PNG/WebP/AVIF,
and 8 test images are AVIF that break naive loaders. Everything here exists so
that never silently corrupts a row.

- `normalize.py` — byte-sniff true format; convert anything (incl. AVIF via
  ImageMagick, since `pillow_heif` is absent) to PNG; resize long edge to 1568px
  (Claude's native vision ceiling; measured object_part 0.85 -> 0.90 vs 1024px);
  assert every image decodes before any model call.
- `authenticity.py` — EXIF signals, perceptual hash, recycled-image detection.
  These FEED `non_original_image` / `possible_manipulation` priors; they never
  decide `claim_status`.
- `cache.py` references the shared content-hash cache so repeated images and
  re-runs never re-pay a model call.

Invariant: assert 111/111 images decode before processing. Explicit error paths
on every decode/convert; never swallow a failure silently.
