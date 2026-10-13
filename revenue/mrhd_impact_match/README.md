# MRHD Impact Match Grant — Match-and-Milestone Evidence Rail

Internal reusable delivery evidence for the approved **Impact Match Grant Match-and-Milestone Evidence Rail** sales motion.

This package is deliberately not an eligibility engine, scoring system, reimbursement authority, applicant portal, compliance certificate, or production integration. It reconciles buyer-approved evidence and arithmetic, preserves immutable lineage, and emits fail-closed HOLD receipts for named human review.

## Program contract encoded

Current MRHD Impact Match public rules used by the synthetic acceptance configuration:

- awards: USD 25,000–250,000 for one-year projects;
- required grantee match: exactly 25% of the awarded amount;
- no more than 50% of the required match may be in-kind;
- focus areas:
  1. Economic Development / Community Improvement / Tourism
  2. Human Services / Health Services
  3. Civic / Public / Charitable / Patriotic / Religious
  4. Leisure / Cultural / Historical
  5. Education
- configured geography:
  - Iowa: Cherokee, Crawford, Ida, Monona, Plymouth, Woodbury
  - South Dakota: Union
  - Nebraska: Dakota

The rail does **not** decide whether an applicant/project is legally eligible, whether evidence is acceptable, whether a valuation is correct, whether a project achieved impact, or whether a reimbursement should be released. MRHD staff / Grant Review Committee / Board retain those decisions.

## What the executable proves

The core `rail.py` consumes deterministic approved-evidence events:

- `AWARD_APPROVED`
- `MATCH_COMMITMENT`
- `CONTRIBUTION_VERIFIED`
- `AMENDMENT_APPROVED`
- `PARTNER_CHANGED`
- `MILESTONE_RECORDED`
- `RETURN_RECORDED`
- `CLOSEOUT_REQUESTED`

It emits one canonical state per approved award; exact integer-cent 25% required-match and 50%-of-required-match in-kind-cap arithmetic; commitment-vs-realized separation; amendment, partner-change and returned-fund lineage; duplicate-safe retry receipts; named-review HOLDs; per-award/cycle totals; and deterministic SHA-256 plus caller-keyed HMAC-SHA256 manifests.

`acceptance.py` is the public buyer-contract wrapper. It additionally detects a repeated applicant+project pair across distinct approved awards, emits `DUPLICATE_APPLICANT_PROJECT`, and **keeps both approved award states visible**. It intentionally does not reject a repeated applicant ID by itself because MRHD's public rules permit some entity types to submit multiple distinct projects.

The caller owns the signing key. This package never stores or returns it.

## Exact 180-record buyer acceptance fixture

`acceptance.build_buyer_acceptance_fixture()` returns **exactly 180 synthetic events** spanning all five focus areas and all eight configured county/state geographies. It deliberately contains:

- duplicate applicant/project IDs across distinct approved awards;
- exact duplicate retries representing timeout-after-commit / interrupted retry;
- changed-content retry under the same event ID;
- duplicate award ID and sequence collision;
- partial/unverified match;
- verified in-kind evidence above the permitted share;
- revised/amended award and match values;
- partner-change lineage;
- late, partial and missed milestones;
- returned funds, return-over-award and over-realized contribution attempts;
- unmatched contribution and unknown award;
- invalid configured geography/category.

No applicant names, beneficiary PII, production finance/grant records, or buyer credentials are present.

## Reproduce

From repository root:

```bash
python -m unittest \
  revenue.mrhd_impact_match.test_rail \
  revenue.mrhd_impact_match.test_acceptance -v
python -O -m unittest \
  revenue.mrhd_impact_match.test_rail \
  revenue.mrhd_impact_match.test_acceptance -v
python -m py_compile \
  revenue/mrhd_impact_match/rail.py \
  revenue/mrhd_impact_match/fixture.py \
  revenue/mrhd_impact_match/acceptance.py \
  revenue/mrhd_impact_match/test_rail.py \
  revenue/mrhd_impact_match/test_acceptance.py
```

The binary acceptance target is not "no HOLDs": the hostile fixture is supposed to prove that ambiguous/invalid evidence remains visibly held. The target is deterministic classification, exact arithmetic, immutable lineage, zero duplicate logical transitions on retry, every approved award visible exactly once, and byte-identical clean-room replay.

## Authority boundary

This is internal evidence supporting a sales/delivery promise. It performs no buyer outreach, payment action, award/reimbursement decision, production mutation, applicant communication, or deployment. A customer-specific delivery remains `HOLD_UNTIL_YES_AND_PAYMENT` under the existing sales lane.
