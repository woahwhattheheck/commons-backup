# Procurement qualification gate

`revenue.procurement_qualification_gate` is a reusable, evidence-bound posture engine for deciding whether a public/private procurement opportunity should be pursued as a direct prime, as bounded paid workshare behind a qualified prime, or not pursued on the current evidence.

It exists because opportunity-specific carriers were repeatedly re-implementing the same qualification question. The gate carries that learning across pursuits without pretending to predict awards.

## Decisions

- `PRIME_READY` — the controlling packet is retained and fresh, the opportunity is open, every prime-applicable mandatory requirement is evidenced, every prime-readiness category is proven/not-required, and pursuit economics remain inside the supplied cap.
- `WORKSHARE_ONLY` — direct-prime evidence is insufficient, but the bounded specialist scope, delivery evidence, paid route, workshare-applicable requirements, source freshness, deadline, and economics remain viable.
- `NO_BID` — neither route is currently supported, the deadline/opportunity is closed, source evidence is stale, or the shared pursuit cost cap is exceeded. A failure that applies only to workshare does not poison an otherwise qualified prime route, and a workshare value floor does not poison prime economics.

`NO_BID` is an evidence-state disposition, not a permanent black list. New controlling evidence or changed economics can be compiled as a new input.

## What it does not do

It does not calculate win probability, buyer score, selected-vendor preference, or causal explanations for an award/loss. It does not select recipients, send outreach, choose Muse, set binding prices, submit bids, sign contracts, move money, create receivables, or recognize revenue. Every such authority bit is fixed false in the result and receipt.

The included `municipal_lims_like_replay.json` is a generic historical-risk fixture: a technically plausible specialist with thin prime past-performance/reference/continuity/assurance evidence routes to `WORKSHARE_ONLY`. Its `source_sha256` binds the retained synthetic bytes in `municipal_lims_like_source.txt`, which is explicitly marked as an internal test source rather than a buyer document. The replay deliberately contains no private personal identifiers and is not represented as the reason any buyer selected another vendor.

## Input contract

All objects are exact-key JSON. Floats and non-finite numbers are rejected by the CLI.

Prime-readiness evidence is required for:

- past performance
- reference coverage
- organizational continuity
- insurance evidence
- security assurance
- deployed product proof
- support capacity
- financial/contract capacity

Workshare readiness is required for:

- bounded specialist scope
- specialist delivery evidence
- a defined paid route

Mandatory requirements say separately whether each buyer requirement applies to the prime and/or to a specialist workshare. This is what lets a missing prime-only corporate credential route the technical slice to teaming instead of killing the opportunity.

Proof states are `PROVEN`, `UNPROVEN`, `FAILED`, or `NOT_REQUIRED`. `PROVEN` requires an evidence reference; `NOT_REQUIRED` may not carry one.

## CLI

```bash
python -m revenue.procurement_qualification_gate compile < opportunity.json > bundle.json
python -m revenue.procurement_qualification_gate verify < bundle.json
```

Bundles bind canonical input and assessment SHA-256 digests and recompile exactly during verification.

## Billings lesson boundary

The City of Billings Bid 1421 non-selection motivated a fresh look at reusable qualification posture, but the City had not supplied a scoring debrief when this module was authored. The historical fixture therefore encodes only an internal risk-management rule: when enterprise-prime evidence is materially thinner than the bounded technical delivery evidence, route to paid workshare. It makes no claim about the City's actual evaluation or selected vendor.
