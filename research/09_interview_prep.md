# AI Judge Interview Prep (grounded in the built system)

30 min, camera on. Grades: technical depth/ownership 40% / judgment 25% /
communication 20% / honesty 15%. Use ownership language ("I chose / I rejected /
I measured / I reverted"). Never narrate the AI.

## 60-second pitch
"I built a damage-claim verifier for car, laptop, and package claims. It is one
agent with internal stages: it extracts the claim from a multilingual chat,
perceives each image objectively, then a deterministic decision tree turns those
image facts into the 14-column output, and a single strict formatter writes the
CSV so no invalid enum can ever escape. Images are the source of truth; user
history and authenticity are risk flags that never flip the verdict. It runs
entirely through Claude Code on my subscription, with no API key. On the 20
labeled rows it gets claim_status 0.75 and object_part 0.80, and I evaluated it
with LOOCV plus stratified folds because at n=20 a single split is meaningless."

## Decisions I own (and the trade-offs)
- **Single agent, internal stages + deterministic post-processor**, not multi-agent.
  The May winner and HackerRank's own data showed single-agent beat multi-agent;
  the decomposition I needed is data-flow, not autonomous negotiation. The
  deterministic tree + formatter make the scored columns reproducible and make
  invalid enums impossible by construction.
- **No API key - Claude Code headless.** I subprocess `claude -p --output-format
  json --model ... --allowedTools Read --add-dir`. I proved it reads images and
  returns parseable JSON, then built a client with retry, a content-hash cache,
  and a temp working directory so the nested call does not re-trigger this repo's
  AGENTS.md. Trade-off: it depends on a logged-in CLI rather than a key, which I
  chose deliberately because I have no API key and the repo is Claude-native.
- **Byte-level image normalization.** I byte-sniff every file because the
  extension lies: 8 test `.jpg` files are actually AVIF that break naive loaders.
  I normalize everything to PNG (ImageMagick for AVIF) and assert all images
  decode. This silently fixes ~18% of the test set most teams miss.
- **Two independent axes:** `valid_image` (is it trustworthy/usable) vs
  `evidence_standard_met` (does it cover the claimed part). case_008 is the proof:
  a clear, evaluable photo that is watermarked stock, so met=true, valid=false.
- **Corrected `manual_review_required`.** My first rule fired it on every
  non-supported row; case_006 in the labels proved that wrong (a benign "retake
  the photo" gap gets no MRR). I tied MRR to history-risk, mismatch, wrong-object,
  authenticity, injection, or unusable images instead.
- **Claim-aware-but-skeptical perception (a measured choice).** I tested three
  perception strategies. Claim-blind perception regressed object_part from 0.80 to
  0.35 because the model no longer knew which part to inspect. Full claim context
  caused sycophancy. The winner gives the claim as a *pointer to the part* but
  tells the model to verify damage independently: claim_status 0.70 -> 0.75,
  object_part to 0.80. I reverted the claim-blind version the moment the number
  dropped.
- **Injection defense as architecture:** in-image text is transcribed as untrusted
  data and flagged `text_instruction_present`; the verdict is still decided on
  pixels (case_020: seal intact, so contradicted, not the injected "approve").

## "How do you know it generalizes to the 44 test rows?" (the key honesty question)
"I do not over-claim from 20 labels. A single 70/30 split there is statistically
meaningless - 6 test rows give a +/-25-point interval. So I report a Wilson 95%
confidence interval (0.53 to 0.89 on claim_status) and stratified 5-fold variance
(0.743 +/- 0.043). The small fold standard deviation is the real signal: the
system is stable across splits, not fit to a lucky one. I also capped my tuning to
a handful of pre-registered changes so I would not overfit by researcher degrees
of freedom, and the decision tree encodes the general labeling philosophy, never
row-specific answers. I never touched the test labels."

## Honest failure modes (volunteer these)
- **Contradicted recall is low (1/5 on sample).** Issue-level semantic mismatch (a
  dent claimed but a scratch shown) and wrong-part damage need an LLM adjudication
  pass over the objective facts; the deterministic tree treats damage on the
  claimed part as supported. This is my #1 next improvement.
- `glass_shatter` / `missing_part` have no sample exemplar - anchored on
  definitions only.
- Severity is coarse and claim-anchored.
- Authenticity uses EXIF + the model's visual read; a well-staged fake passes.

## Likely questions -> short answers
- *Why deterministic over an all-LLM decider?* Reproducibility and zero invalid
  enums; the LLM proposes facts, code disposes the verdict.
- *Why Sonnet not Opus for vision?* Bulk per-image work; Sonnet is enough and the
  two-stage design keeps it cheap. Opus is reserved for the adjudication pass.
- *Biggest risk in production?* Contradicted recall and staged-fraud images; I
  route low-confidence and all authenticity/mismatch cases to manual review.
- *What did AI do vs you?* I designed the architecture, the decision-tree rules,
  the evaluation methodology, and drove every calibration decision; I used AI to
  write modules to my spec and to research prior art and eval methodology, which I
  then verified (e.g. I personally confirmed the 8 AVIF files and the n=20 CI math).
