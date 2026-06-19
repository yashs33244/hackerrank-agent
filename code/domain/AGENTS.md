# code/domain/ — AGENTS.md

The deterministic core. No LLM calls live here; this is the logic the judge can
read top-to-bottom and trust.

- `enums.py` — the closed output vocabularies (single source of truth; do not edit
  values without updating `problem_statement.md`).
- `constants.py` — static tables: `OUTPUT_COLUMNS`, `OBJECT_PART_VOCAB`,
  `RISK_FLAG_CANONICAL_ORDER`.
- `types.py` — the typed pipeline state (`ClaimState`, `ImageFact`,
  `ExtractedClaim`, `EvidenceRule`, `ClaimOutput`).
- `evidence_rules.py` — loads `evidence_requirements.csv`, maps a claim to its
  minimum-evidence rule.
- `history.py` — loads `user_history.csv`, derives `is_risky`.
- `decision_tree.py` — S4. Turns per-image facts + claim + rule + history into a
  `ClaimOutput`. Calibrated to all 20 sample labels.

Invariants: `valid_image` (trust) and `evidence_standard_met` (coverage) are
independent. `manual_review_required` fires only on history-risk / mismatch /
wrong-object / authenticity / injection / unreviewable images, never on a benign
coverage gap alone. History never flips `claim_status`.
