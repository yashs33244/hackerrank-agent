# code/evaluation/ — AGENTS.md

The required evaluation workflow. Scores the system on the 20 labeled
`dataset/sample_claims.csv` rows before producing the final `output.csv`.

- `metrics.py` — per-column exact-match accuracy (6 enums + 2 bools), `claim_status`
  3x3 confusion matrix, `risk_flags` multi-label F1/Jaccard, `supporting_image_ids`
  set match, per-object (car/laptop/package) breakdown. Pure functions over dicts.
- `main.py` — `python code/evaluation/main.py`: read predicted + gold CSVs, align by
  `(user_id, image_paths)`, print the report.
- `compare.py` — tabulate the >=2 required strategy/model configurations side by
  side, so the final choice for `output.csv` is justified by data.
- `evaluation_report.md` — accuracy + strategy comparison + operational analysis
  (model calls, tokens, images, cost incl. the subscription/no-key note, latency,
  rate-limit/caching strategy).

Invariant: the 20 labels are a calibration/holdout signal only. Never hardcode
test answers or tune against `claims.csv` (the README forbids it).
