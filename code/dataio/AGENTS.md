# code/io/ — AGENTS.md

Read inputs, guarantee a schema-valid output.

- `reader.py` — read `claims.csv` / `sample_claims.csv` (UTF-8, multiline-safe),
  split `image_paths` on `;`.
- `schema.py` — Pydantic v2 `OutputRow` typed by the enums + `coerce_output`,
  which CLAMPS any illegal model value to a safe legal one (off-vocab enum →
  `unknown`/`none`; wrong-object part → `unknown`; empty risk_flags → `["none"]`).
  It never raises on bad model output.
- `formatter.py` — the SINGLE CSV write path. Emits `OUTPUT_COLUMNS` order,
  lowercase booleans, `;`-joined bare tokens or literal `none`, bare image IDs
  (`img_2` not `img_2.jpg`), echoed input columns verbatim, double-quoted, UTF-8.

Invariant: no other module may serialize a CSV row. If it is wrong here, it is
wrong everywhere, so all 14-column formatting rules live in exactly one place.
