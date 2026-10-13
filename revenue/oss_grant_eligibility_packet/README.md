# OSS grant eligibility packet compiler

`revenue.oss_grant_eligibility_packet` compiles a **mechanical grant-packet readiness** assessment from one exact retained program-rule generation plus source-bound project/repository evidence.

`PACKET_READY` does **not** mean eligible, selected, funded, awarded, paid, or revenue-recognized. It means only that the mechanically checkable eligibility/artifact gates in the retained generation have evidence. Subjective selector criteria remain `HOLD` and never become eligibility facts.

## Current retained programs

`reference_programs.json` binds the Commons PR #15153 OSS sponsor-route-map generation (Git blob `9a5b6075986d8259b241861e0a9bac5bf1d178f4`) and a current first-party recensus performed 2026-09-17:

- GitHub Secure Open Source Fund — rolling applications; current-maintainer/applicant-region/license/governance/participation gates; advertised $10,000 per selected project remains **reference only**.
- NLnet Open Internet Stack / Restack — current deadline November 3, 2026 at noon CET; technical-development/open-license/European-dimension gates. NLnet's current proposal guidance says it is not interested in AI-generated projects/proposals, so this generation sets `OWNER_AUTHORED_ONLY`: the compiler emits no AI-generated application outline for NLnet.
- Sovereign Tech Fund — open digital base technology, estimated project cost over €50,000, no duplicate public financing for the same activities, FOSS/open-documentation licensing, and no prototype/user-facing-app requests under the current criteria. Prevalence/relevance/vulnerability/expertise remain selector HOLDs.
- OTF Internet Freedom Fund — rolling; advertised $10,000–$900,000 / up to 24 months and sanctions constraints are mechanical reference gates; mission/cost-effectiveness/sustainability/complementarity remain selector HOLDs.
- OTF Surge and Sustain Fund — retained as `SOURCE_CONFLICT`: the first-party fund page and application portal surfaced different October 2026 deadline dates in the recensus. The compiler therefore emits `HOLD_PROGRAM_CURRENTNESS`, regardless of project fit, until that source conflict is reconciled.
- OTF FOSS Sustainability Fund — retained as `NOT_ACCEPTING` because the current first-party fund page says applications are not currently being accepted. The compiler therefore emits `HOLD_PROGRAM_CURRENTNESS`.

Reference facts are retained normalized facts with `source_factset_sha256`; they are **not represented as hashes of the remote HTML bytes**. The route-map Git blob and reference-program file bytes are independently bound so any local rule-generation change requires a new digest.

## Reference-generation currentness

Program facts can change independently of project evidence, so `PACKET_READY` is additionally fenced by a **code-owned seven-day currentness horizon** (`REFERENCE_GENERATION_MAX_AGE_SECONDS = 604800`). The caller cannot widen or disable this horizon through the input document.

Both clocks must be current relative to `input.evaluated_at`:

- top-level `reference_programs.json.generated_at`;
- the selected program's `observed_at`.

If either timestamp is in the future or more than seven days old, packet state is `HOLD_PROGRAM_CURRENTNESS` even when every project fact is fresh and mechanically verified. The packet retains the policy horizon, both ages, and a deterministic `REFERENCE_GENERATION_CURRENT | REFERENCE_GENERATION_STALE | REFERENCE_GENERATION_FUTURE` reason. Existing `SOURCE_CONFLICT`, `NOT_ACCEPTING`, and closed-program holds still take the same program-level precedence and can never be bypassed by fresh project evidence.

This is intentionally a **recensus requirement**, not an automatic network refresh. Before a stale generation can become ready again, re-open the listed first-party sources, create a new retained generation, and rerun the compiler.

## Gate model

Each rule has a scope:

- `ELIGIBILITY` — mechanically testable program constraint.
- `ARTIFACT` — mechanically testable required evidence/artifact presence.
- `SELECTOR` — subjective or comparative reviewer judgment. These always remain `HOLD / SUBJECTIVE_REVIEW_REQUIRED`, even if a caller supplies a flattering self-assessment.

Every gate emits only:

- `VERIFIED`
- `MISSING`
- `HOLD`

Program-level packet state is one of:

- `PACKET_READY` — program generation is within the code-owned currentness horizon and every mechanical eligibility/artifact gate is verified. Selector HOLDs are retained and do not imply ineligibility.
- `OWNER_FACTS_REQUIRED` — at least one mechanical fact/artifact is missing.
- `HOLD_SOURCE_CONFLICT` — a mechanical gate has contradictory/stale/future project evidence or does not satisfy a retained mechanical constraint.
- `HOLD_PROGRAM_CURRENTNESS` — program is closed/not accepting, retained first-party sources conflict, or the retained bundle/program observation is stale/future.

## Project evidence

Each project fact carries:

- stable evidence id and evidence key;
- typed value (boolean, integer, string, or bounded list);
- source reference and SHA-256;
- observation timestamp;
- authority label.

Multiple current sources for one evidence key must agree byte-semantically on the value. Disagreement is `HOLD`. Future or older-than-policy evidence is `HOLD`. Missing evidence is `MISSING`.

The compiler does not fetch repository state and does not turn technical fit into eligibility. Acquisition/capture is a separate evidence step.

## Application outline behavior

For programs permitting AI-assisted packet structuring, the output contains only program prompt headings plus IDs of verified evidence; it deliberately generates **no application prose**. The owner must author/review any final application.

For the current NLnet generation, `OWNER_AUTHORED_ONLY` makes the outline empty and explicitly instructs the owner to author application text. This is intentional compliance with the currently retained first-party proposal guidance.

## Run

```bash
OUT="$(mktemp -d)/grant"
python -m revenue.oss_grant_eligibility_packet compile \
  --programs revenue/oss_grant_eligibility_packet/reference_programs.json \
  --input revenue/oss_grant_eligibility_packet/fixtures/synthetic_project.json \
  --out-dir "$OUT"

python -m revenue.oss_grant_eligibility_packet verify \
  --programs revenue/oss_grant_eligibility_packet/reference_programs.json \
  --input revenue/oss_grant_eligibility_packet/fixtures/synthetic_project.json \
  --packet "$OUT/packet.json" \
  --markdown "$OUT/packet.md" \
  --receipt "$OUT/receipt.json"
```

Outputs are create-exclusive and never overwrite existing files. The receipt binds exact input bytes, exact reference-program bytes, program factset digest, route-map Git blob generation, packet bytes, and Markdown bytes.

## Updating program rules

1. Re-open the exact first-party sources listed in the retained program entry.
2. Update normalized `source_facts`, `rules`, `observed_at`, program state, and any first-party conflicts; set top-level `generated_at` to the new retained generation time.
3. Recompute each `source_factset_sha256` from canonical JSON of the exact `source_facts` array.
4. If Commons' sponsor route map changed, update the retained Git blob SHA-1 and route source ids together.
5. Run the full normal + `python -O` suite and CLI compile/verify.
6. Never silently change a selector judgment into an eligibility gate.

## Authority ceiling

The compiler authorizes none of the following: application submission, portal/form mutation, email/DM, sponsor contact, Muse request, signature/certification, price commitment, eligibility guarantee, selection/award claim, payment/cash claim, or accounting revenue recognition.
