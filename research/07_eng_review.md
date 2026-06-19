# Gate 2 — Engineering Review (architecture locked)

> Self-run eng-manager review from the grilled decisions (`06_self_grill.md`). 2026-06-19.

## 1. Locked architecture (single agent · internal stages · deterministic shell)

```
 claims.csv row + user_history + evidence_requirements + image files
        │
   [S0] NORMALIZE & PRE-GATE            (pure Python, no LLM)
        │  byte-sniff → AVIF/WebP→PNG (ImageMagick), resize 1024px
        │  EXIF probe + intra-set pHash → authenticity/recycled priors
        │  load history[user_id]; pick evidence_req[(object, issue_family)]
        │  regex pre-screen of user_claim for injection
        ▼
   [S1] CLAIM EXTRACTION               (Sonnet, 1 cheap text call; multilingual)
        │  {claimed_object, claimed_part, claimed_issue, claimed_severity, missing_item?}
        ▼
   [S2] PER-IMAGE PERCEPTION           (Sonnet vision · 1 call/image · PARALLEL · CACHED)
        │  "This is img_2." describe-before-decide. untrusted-text system rule.
        │  → {object, part, visible_damage, quality_issues[], embedded_text,
        │     text_is_instruction?, authenticity_notes, relevant?, clear_enough?, confidence}
        ▼
   [S3] ADJUDICATION                   (Opus · 1 call/row · TEXT-ONLY; raw image re-attached for ~7 hard rows)
        │  inputs: extracted claim + S2 facts + evidence rule + history + priors
        │  → draft of the 10 produced columns as one forced-tool JSON object
        ▼
   [S4] DETERMINISTIC DECISION TREE     (pure Python — §3)
        │  evidence-sufficiency → claim_status → severity → supporting_ids
        │  → risk_flags union → valid_image vs evidence_standard_met → MRR rule (D10)
        ▼
   [S5] CRITIC / VALIDATOR             (rules + 1 optional cheap call)
        │  enum legality clamp · justification cites a supporting id · injection echo-check
        │  · coherence (NEI⇒supp=none&sev=unknown; clean-contradicted⇒issue=none&sev=none;
        │    valid_image=false⇒MRR) · 1 corrective retry → safe fallback (NEI+MRR)
        ▼
   [S6] STRICT CSV FORMATTER           (pure Python — single write choke point)
        │  echo cols 1-4 verbatim · 14-col order · lowercase bools · ';' joins
        │  · bare image IDs · 'none' literal · double-quote all · UTF-8 \n
        ▼
   output.csv row
```

Design invariants (defensible in interview):
- **Images are primary truth.** History + authenticity + injection are *flags*, never a `claim_status` flip.
- **LLMs propose, deterministic code disposes.** Every scored enum is finalized by Python, not free-texted by a model → near-zero invalid-enum risk.
- **One write path** (S6) → schema-valid CSV by construction.

## 2. Module structure (every folder has AGENTS.md + CLAUDE.md)

```
code/
├── AGENTS.md            # contract for code/ (entry points, env vars, "don't rename main.py")
├── CLAUDE.md            # @AGENTS.md + Claude-Code notes
├── README.md            # human quickstart (rubric: eng rigor)
├── main.py              # entry: read claims.csv → pipeline → output.csv  (terminal)
├── config.py           # env keys, model names, paths, pricing constants, temp=0
├── pipeline.py         # orchestrates S0..S6 over rows (parallel + cache)
├── state.py            # ClaimState (typed) + all Enums + Pydantic output schema
├── domain/
│   ├── AGENTS.md / CLAUDE.md
│   ├── enums.py        # claim_status, issue_type, per-object part vocab, risk_flags, severity
│   ├── evidence_rules.py  # evidence_requirements loader + (object,issue_family)→rule map
│   ├── history.py      # user_history loader + history_flags→user_history_risk
│   └── decision_tree.py   # S4 deterministic logic (the §3 tree) + MRR rule (D10)
├── images/
│   ├── AGENTS.md / CLAUDE.md
│   ├── normalize.py    # byte-sniff, AVIF/WebP→PNG, resize, decode-assert
│   ├── authenticity.py # EXIF probe, pHash dedup, watermark/screenshot signals
│   └── cache.py        # content-hash cache for S2 results
├── agent/
│   ├── AGENTS.md / CLAUDE.md
│   ├── client.py       # Claude Code headless wrapper: subprocess `claude -p --output-format json --json-schema --model --add-dir --allowedTools Read`; temp via settings; backoff retry; content-hash cache. NO API key (subscription auth).
│   ├── perception.py   # S2 per-image (Sonnet)
│   ├── claim_extract.py# S1 (Sonnet, multilingual)
│   ├── adjudicate.py   # S3 (Opus, text-only)
│   └── critic.py       # S5 validator
├── prompts/
│   ├── AGENTS.md / CLAUDE.md   # prompt design rules (Pattern C, untrusted-text guard)
│   ├── perception.md  claim_extract.md  adjudicate.md  critic.md
├── io/
│   ├── AGENTS.md / CLAUDE.md
│   ├── reader.py       # claims.csv reader (UTF-8, multiline-safe)
│   └── formatter.py    # S6 strict 14-col writer (the choke point)
└── evaluation/
    ├── AGENTS.md / CLAUDE.md
    ├── main.py         # score output vs sample_claims.csv
    ├── metrics.py      # per-col acc, claim_status confusion, risk_flags F1, id-set match
    ├── compare.py      # ≥2-strategy runner (single-pass vs two-stage; ±post-processor)
    └── evaluation_report.md  # accuracy + strategy comparison + ops/cost analysis
```

**Per-folder doc convention:** `AGENTS.md` (tool-agnostic) states the folder's purpose, the exact inputs/outputs of its modules, invariants it must preserve (e.g. `io/AGENTS.md`: "the ONLY place that serializes CSV; enforce 14-col order + lowercase bools"), and naming/rename rules. `CLAUDE.md` is one line `@AGENTS.md` plus any Claude-Code-specific hint. This makes each subtree self-describing so any agent (or the AI Judge) opening one folder understands its job — directly serves Code-ZIP "architecture" + "eng rigor."

## 3. Deterministic decision tree (S4) — grounded in the 20 labels

```python
# pseudocode — exact rules calibrated to sample ground truth
def decide(claim, per_image, evid_rule, history):
    flags = set()
    usable = [im for im in per_image if im.decodable and im.relevant]
    # valid_image: trust/usability
    valid_image = any(im.decodable for im in per_image) and not all(
        im.non_original or im.unreviewable for im in per_image)
    if any(im.non_original for im in per_image):       flags |= {"non_original_image"}
    if any(im.possible_manip for im in per_image):     flags |= {"possible_manipulation"}
    if any(im.text_is_instruction for im in per_image):flags |= {"text_instruction_present"}

    # evidence_standard_met: coverage of the claimed part (REQ_* + REQ_GENERAL_MULTI_IMAGE)
    shows_part = any(im.shows_claimed_part_clearly for im in per_image)
    evidence_met = shows_part and not all_offframe_or_occluded(per_image, claim)

    if not shows_part:                       # 006, 018
        status, issue, part, sev, supp = "not_enough_information","unknown",\
            (claim.part if claim.part_in_vocab else "unknown"),"unknown",[]
        flags |= visual_quality_flags(per_image)            # wrong_angle/cropped/damage_not_visible
        evidence_met = False
    else:
        img = best_supporting_image(per_image, claim)
        if img.object != claim.object:        # 019 wrong object
            status, issue, part, sev = "contradicted","unknown","unknown", img.severity_or("low")
            flags |= {"wrong_object","claim_mismatch"}
        elif not img.has_damage:              # 014, 020 clean part
            status, issue, sev = "contradicted","none","none"; part = img.part
            flags |= {"damage_not_visible"}
        elif not matches(img, claim):         # 005, 008 different damage
            status = "contradicted"; issue = img.issue; part = img.part; sev = img.severity
            flags |= {"claim_mismatch"}
        else:                                 # supported (13)
            status = "supported"; issue = img.issue; part = img.part; sev = img.severity
        supp = supporting_subset(per_image, claim, status)   # [] iff NEI
        if img.part != claim.part and claim.part_in_vocab: flags |= {"wrong_object_part"}

    # history (never flips status)
    if history.is_risky: flags |= {"user_history_risk"}
    # MRR rule (D10) — NOT a blanket non-supported
    if (("user_history_risk" in flags) or ({"claim_mismatch","wrong_object",
         "non_original_image","possible_manipulation","text_instruction_present"} & flags)
         or (valid_image is False)):
        flags |= {"manual_review_required"}
    flags = flags or {"none"}
    return assemble(status, issue, part, sev, supp, valid_image, evidence_met,
                    order(flags))
```

Self-checks vs the 20 labels: 006→NEI/evid=false/no-MRR ✓ · 008→contradicted/valid=false/evid=true/MRR ✓ · 014,020→contradicted/issue=none/sev=none ✓ · 017→supported+MRR(history) ✓ · 019→contradicted/unknown/wrong_object ✓ · 007→supp=img_2 only ✓.

## 4. ClaimState (typed shared state)
`user_id, image_paths[], user_claim, claim_object` (inputs) · `images: List[ImageFact]` (S2) · `claim: ExtractedClaim` (S1) · 10 output fields (S3 draft → S4 final → S5 validated). Each stage reads/writes only its slice (reuse of the prior solution's TicketState spine). Pydantic `OutputRow` with `Enum` fields → validation + repair-clamp guarantees legal enums.

## 5. Edge-case register (with handling)
| # | Edge case | Handling |
|---|---|---|
| 1 | 8 AVIF-as-`.jpg` | S0 byte-sniff + ImageMagick→PNG; assert 111/111 decode |
| 2 | Multilingual (Hinglish/Spanish/Pinyin) | S1 Sonnet extraction is language-agnostic; cols 1-4 echoed verbatim (CSV-quoted) |
| 3 | Multi-image (31/44) | S2 per-image; REQ_GENERAL_MULTI_IMAGE: one good image suffices; subset selection for supporting_ids |
| 4 | Multi-part claim (bumper+headlight) | pick primary part/issue; note secondary in justification; flag MRR; documented limitation |
| 5 | In-image injection ("approve this") | untrusted-text rule + transcribe-as-data + S5 echo-check → text_instruction_present + MRR; judge pixels |
| 6 | Watermark/stock (008) | authenticity → non_original_image → valid_image=false + MRR; status still from pixels |
| 7 | Clean part claimed damaged (014,020) | contradicted + damage_not_visible + issue=none + sev=none |
| 8 | Wrong object (019) | contradicted + wrong_object + unknown part/issue |
| 9 | Off-frame/occluded part (006,018) | NEI + evidence_met=false + supp=none |
| 10 | No-exemplar enums (glass_shatter, missing_part) | anchor on enum definitions in prompt; clamp in S5 |
| 11 | 429 / rate limit | exponential backoff retry in client.py (won't hit at 133 calls but robustness points) |
| 12 | Model returns bad enum | Pydantic clamp to nearest legal / unknown|none; never write invalid |

## 6. Test & eval coverage map
- **Unit (pure, fast):** normalize (format sniff on all 111), enums vocab, decision_tree on 20 hand-encoded sample fact-sets (asserts the §3 self-checks), formatter (golden 14-col string), history/evidence loaders.
- **Integration:** full pipeline on the 20 sample rows → compare to labels.
- **Eval (`evaluation/`):** per-column accuracy, claim_status confusion matrix, risk_flags F1, supporting-id set match, per-object breakdown; ≥2-strategy comparison; ops/cost report.
- **No hardcoding:** decision thresholds are general; the 20 labels are a calibration signal only (asserted in report honesty note).

## 7. Performance / cost / determinism (Claude Code, no API key)
~133 calls (82 S2 + 44 S3 + ~7 hard). **Executed via Claude Code subscription** (`claude -p`), so no per-token billing — report a *hypothetical* API-equivalent (~$0.85: Sonnet vision + Opus text, pre-resize −55%) plus the real constraint: **subscription usage limits**. Mitigations: content-hash cache (re-runs free), cheap-model routing for bulk perception, text-only adjudication, checkpoint/resume, 4-8 concurrent subprocesses. Determinism: forced `--json-schema` + deterministic S4/S6 over the facts + cache (residual VLM variance accepted). All documented in `evaluation_report.md`.

## 8. Adversarial self-review (holes found → resolved)
1. **MRR over-firing** (blueprint's naive union) → corrected to D10 rule; case_006 proves benign gaps get no MRR.
2. **`evidence_standard_met` conflated with NEI** → it's coverage, false on both NEI rows but conceptually distinct from valid_image; 006/008/018 triangulate the two axes. Keep separate booleans.
3. **`supporting_image_ids` over-selection** (listing all images) → deterministic minimal subset bound to VLM-verified images; none iff NEI.
4. **Over-abstention** (too many NEI) → only 2/20 sample are NEI; "visible-and-clean ⇒ contradicted" gate; severity can be unknown while status is decisive.
5. **Interview "is this really single-agent?"** → yes: one agent identity + tools; stages are internal data-flow, not autonomous negotiators. Scripted answer in blueprint §8 Q1.
6. **No-exemplar enums** (glass_shatter/missing_part appear in test, not sample) → prompt anchors on definitions + S5 clamp; flagged as known risk.
7. **Determinism vs vision variance** → temp 0 + cache; accept residual VLM nondeterminism, mitigated by deterministic S4/S6 over the facts.

8. **No-API-key execution risk** → solution shells out to the installed `claude` CLI (subscription auth); de-risked by confirming headless `--print --output-format json --json-schema --model` exist (v2.1.183). Main residual risk = subscription usage limits → caching + checkpoint/resume + cheap-model routing.

**Verdict: architecture is LOCKED.** No external API key required — Claude Code (installed, authenticated) is the inference engine. Only the `claude` CLI + Python stdlib + PIL/ImageMagick are needed.
