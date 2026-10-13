# Bias Bounty Mapping Equity — deterministic scorer carrier

This directory is a reproducible, **data-free** implementation carrier for the Zindi / Humane Intelligence **Bias Bounty Mapping Equity Challenge**. It turns tract-level aggregates from the challenge-provided sources into the organizer-published coverage-gap formula, compiles a minimal `GEOID,coverage_gap_score` submission, and emits a deterministic receipt that can be verified offline.

It does **not** register an account, download the challenge corpus, submit to Zindi, or claim any leaderboard result, award, payment, or revenue.

## Paid target

Public challenge: `https://zindi.world/competitions/bias-bounty-mapping-equity-challenge`

Public dataset/readme: `https://source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/`

At carrier creation the challenge advertised a $10,000 USD pool, with $4,500 / $2,500 / $1,500 leaderboard awards, a $1,000 Best Bias Discovery award, and a $500 Best Documentation award, closing 2026-10-31. The public dataset pins Overture to release `2026-08-19.0`.

## What the scorer binds

For each census tract, upstream aggregation must produce exactly these columns:

```text
GEOID,
overture_road_length,tiger_road_length,
overture_buildings,microsoft_buildings,
overture_fire,hifld_fire,
overture_ems,hifld_ems,
overture_schools,hifld_schools,
overture_places,cbp_establishments
```

`GEOID` is an **11-digit string**. Do not allow a spreadsheet or dataframe import to coerce it to an integer; leading zeroes are part of identity.

For any observed/reference pair with a positive reference, the component deficit is:

```text
1 - min(1, observed / reference)
```

A zero reference makes that component **undefined**. Undefined components are omitted from the relevant mean; they are never silently converted to either zero or one.

The public challenge methodology maps those quantities as follows:

- **Transport:** Overture length for named highways in classes `motorway`, `trunk`, `primary`, `secondary` versus TIGER/Line roads with MTFCC `S1100` or `S1200`. Upstream length aggregation must use a defensible projected/metric geometry workflow; this carrier deliberately does not hide CRS decisions inside the scorer.
- **Buildings:** Overture building count versus Microsoft US Building Footprints count. ACS housing is context only and is **not** the denominator.
- **Critical facilities:** per-type gaps for HIFLD fire stations, EMS stations, and public schools; the HIFLD half is the mean of whichever reference types are defined in that tract.
- **Establishments:** all Overture places versus Census County Business Patterns establishment count.
- **POI:** mean of the defined HIFLD half and CBP half.
- **Composite:** mean of the defined transport, building, and POI components.

A tract for which all three top-level components are undefined is refused rather than assigned a fabricated score.

## Why the aggregation boundary is explicit

The expensive/geospatial stage and the scoring stage have different failure modes. Keeping tract aggregation as an explicit artifact makes the following auditable before any provider submission:

1. Overture release and feature filters.
2. TIGER MTFCC filter and length CRS.
3. Point/polygon tract assignment and boundary policy.
4. County Business Patterns tract allocation method supplied by the challenge.
5. Exact authoritative tract universe from the challenge sample submission.
6. No accidental use of reference/answer columns as scorer inputs.

The aggregate reader accepts **only** the schema above. A `coverage_gap_score` or other extra column is rejected; this prevents a published reference-score artifact from silently contaminating the scored pipeline.

## Run the synthetic proof

```bash
python -m unittest -v test_mapping_equity.py
python -O -m unittest -v test_mapping_equity.py
python -m py_compile mapping_equity.py test_mapping_equity.py
```

Build from a tract aggregate CSV plus the challenge sample-submission file used only as the authoritative GEOID universe:

```bash
python mapping_equity.py build \
  --aggregates aggregates.csv \
  --authoritative SampleSubmission.csv \
  --output submission.csv \
  --receipt submission.receipt.json
```

Verify later without recomputing geospatial joins:

```bash
python mapping_equity.py verify \
  --submission submission.csv \
  --receipt submission.receipt.json \
  --authoritative SampleSubmission.csv
```

Outputs are create-exclusive. The tool never pathname-deletes an output after creation failure; a partial failure is preserved for diagnosis and must be retried with fresh output paths.

## Submission discipline

Before a real Zindi submission, separately record:

- exact challenge dataset object identities / ETags / byte hashes where available;
- exact Overture release (`2026-08-19.0` for this carrier generation);
- aggregation code/version and environment;
- tract aggregate file SHA-256;
- authoritative sample-submission SHA-256;
- scorer source commit;
- generated CSV and receipt SHA-256;
- challenge account/team identity and actual provider submission ID only after the provider returns it.

Do not convert local validation into a leaderboard, eligibility, prize, payment, or revenue claim.

## Competition-side next work

The high-leverage next execution is a **public-data aggregation runner** that streams the four Source Cooperative study regions, emits the exact aggregate schema above, and records source object hashes and CRS/filter decisions. Keep scored computation restricted to the challenge-provided datasets. Any extra public data belongs in a separately labeled Best Bias Discovery analysis and must not feed `coverage_gap_score`.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
