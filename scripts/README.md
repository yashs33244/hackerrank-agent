# Dev Scripts (Not Part of Deliverable)

These scripts are development tools for iterative quality improvement.
They are **not** included in the evaluable submission — see `code/` for that.

## evaluate.py

Scores `support_tickets/output.csv` against `support_tickets/sample_support_tickets.csv`.

```bash
# From repo root
python scripts/evaluate.py

# Against a specific output file
python scripts/evaluate.py --output path/to/output.csv
```

**Scoring rubric (4 points per ticket):**

| Dimension | Points | Criterion |
|---|---|---|
| `status_match` | 1.0 | Exact match (replied / escalated) |
| `product_area_sim` | 1.0 | Jaccard token overlap |
| `request_type_ok` | 1.0 | Exact match |
| `response_quality` | 1.0 | Length > 50 chars AND not a canned fallback |

Saves a JSON report to `scripts/eval_report.json`.

## improve_loop.py

Iteratively refines a specified agent's system prompt using LLM-generated patches.

```bash
# Improve the triage prompt (5 iterations)
python scripts/improve_loop.py --agent triage --iterations 5

# Improve the router prompt (3 iterations)
python scripts/improve_loop.py --agent router --iterations 3
```

**Algorithm:**
1. Run pipeline on sample tickets
2. Score against ground truth
3. Build a failure summary for low-scoring tickets
4. Ask Gemini to propose a minimal prompt patch
5. Apply patch and re-run
6. Repeat until score ≥ 95% or max iterations reached

Checkpoints (prompt snapshot + score) are saved to `scripts/improve_checkpoints/`.
