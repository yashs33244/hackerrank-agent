# Claim Adjudication (per-attribute comparison, Stage S3)

You compare ONE user claim against the objective facts already extracted from the
images by a prior stage. You do NOT see the raw images. Judge each attribute
INDEPENDENTLY and skeptically: do not assume the claim and the image facts agree.
Your job is to catch disagreements a naive reader would miss.

CLAIM (what the user asserts):
{claim_json}

IMAGE FACTS (objective, one entry per image):
{image_facts_json}

For each attribute output exactly one token:

- `object_cmp`: does any image show the claimed object? -> `match` | `mismatch` | `unknown`
- `part_cmp`: is the claimed part the one actually shown/affected? -> `match` | `mismatch` | `unknown`
- `issue_cmp`: does the visible damage match the claimed TYPE of damage?
    - `match` = the same kind of damage, OR worse damage that clearly INCLUDES the
      claimed kind (a claimed dent shown as a crushed or broken panel is still a
      match, because the dent is present within the worse damage).
    - `different_issue` = a clearly DIFFERENT kind of damage (claimed a dent but
      only a surface scratch is visible; claimed a crack but only a stain). This
      is a CONTRADICTION, not insufficient evidence.
    - `none_visible` = the claimed part is shown but has no damage at all.
    - `unknown` = the part or damage cannot be determined from the facts.
- `severity_cmp`: is the severity roughly consistent? -> `match` | `mismatch` | `unknown`
- `supporting_image_id`: the image id (e.g. `img_2`) that best supports your
  reading, or `none`.
- `falsifies_claim`: boolean. Is there clear evidence the claim is FALSE (a
  different kind of damage on the matching part, or no damage where damage is
  claimed)?

Decision discipline: a `different_issue` or `none_visible` on a matching part means
the specific claim is contradicted. Do not soften a real disagreement into
`unknown` to avoid committing.

Return ONLY a JSON object with exactly these keys: `object_cmp`, `part_cmp`,
`issue_cmp`, `severity_cmp`, `supporting_image_id`, `falsifies_claim`. No prose.
