# Zindi Bias Mapping Equity 2026 — Best Bias Discovery plan

Public-safe research artifact for the separately judged **$1,000 Best Bias Discovery** award. This is a preregistered hypothesis and falsification plan, not a measured disparity finding, leaderboard model, or competition submission.

## Boundary

- Use the four current scored-region GEOID templates and organizer-provided Source Cooperative strata as the cohort authority.
- Use only currently permitted Overture/ACS inputs for coverage evidence. Do not reacquire or reconstruct removed target/reference layers.
- Keep any later public contextual dataset confined to the narrative analysis. It must never enter the RMSE prediction pipeline.
- Preserve GEOID as 11-digit text and validate provenance with `../validate_contract.py`.
- Freeze the cohort definitions and model below before inspecting any leaderboard feedback.

## Primary hypothesis: Eastern Oklahoma boundary-type blind spot

The organizer's standard scorecard collapses tribal geography to tribal/non-tribal. The supplied tract strata distinguish legal and statistical boundary types. The preregistered question is:

> After matching on rurality, density, population, SVI, and drought exposure, do Eastern Oklahoma legal-boundary tracts show lower permitted Overture coverage or a materially different upstream-source mix than statistical-area tracts?

The released source preflight recorded these cohort summaries from the organizer strata; they are navigation evidence only and must be recomputed from the pinned input before analysis:

| Cohort | n | Mean SVI | Mean summer D2+ drought | Mean nearest GHCN distance | Mean RUCA density |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legal-only | 13 | 0.582 | 16.78% | 10.05 km | 256 |
| Statistical-only | 792 | 0.604 | 9.56% | 5.80 km | 1,166 |

This comparison is outside the fixed five-way scorecard because it tests **within-tribal boundary type**, rather than repeating the tribal/non-tribal slice.

### Coverage evidence

Compute tract-level evidence from the permitted current Overture release only:

1. building count per supplied ACS housing unit;
2. building area per housing unit;
3. road length per square kilometre and named-road share;
4. POI and infrastructure counts per 1,000 residents and per square kilometre;
5. non-null upstream source-provider shares for buildings, roads, POIs, and infrastructure;
6. input missingness flags for every evidence family.

Every feature row must carry its source path and extraction rule in a machine-readable provenance manifest. Source-provider nulls are missing data, not a provider category.

### Frozen matching design

1. Restrict to the exact Eastern Oklahoma scored GEOID set.
2. Exclude tracts whose boundary type is absent or ambiguous; report the exclusion count.
3. Define treatment as `legal-only`; comparison as `statistical-only`. Do not merge mixed/overlapping types into either cohort.
4. Build comparison strata before reading the coverage evidence:
   - rural/urban class;
   - RUCA-density quintile within Eastern Oklahoma;
   - population quintile;
   - SVI quintile;
   - summer D2+ drought quartile.
5. Match each legal-only tract to up to five statistical-only tracts in the same rural/urban class, minimizing rank distance across the other four strata. Matching is without replacement within a legal tract but comparison tracts may support more than one legal tract; report reuse.
6. Fail closed when a legal tract has no comparison in the same rural/urban class and within one bin on all other covariates. Report unmatched GEOIDs; do not widen silently.
7. Estimate paired median and mean differences for each raw evidence family. Use the coverage proxy only as a summary, never as sole evidence.
8. Quantify uncertainty with a fixed-seed (`20261006`) matched-set bootstrap of 10,000 resamples. Because the treated cohort is small, report intervals and individual treated-tract contributions; do not rely on asymptotic p-values.

### Promotion rule

Promote the hypothesis into a prize writeup only when all conditions hold:

- at least 10 of the 13 recorded legal-only tracts remain eligible after fresh input validation;
- at least 80% of eligible legal-only tracts receive a valid match;
- the preregistered coverage summary and at least one raw Overture family move in the same direction;
- the directional effect remains after omitting each legal-only tract in turn;
- missingness and one extreme tract do not explain the result;
- source-provider composition is reported separately from feature density.

Falsify or label inconclusive if matching explains the raw difference, the effect changes sign under leave-one-out analysis, raw evidence disagrees with the summary proxy, or the result is driven by missing inputs.

## Confirmatory interaction: rural × tribal overlap × drought

If the boundary-type hypothesis is inconclusive, test one frozen secondary question without redefining thresholds:

- region: Eastern Oklahoma;
- rural: organizer-provided rural class;
- high tribal overlap: `tribal_pct >= 0.5`;
- high drought: top-quartile summer D2+, threshold recorded as `>= 13.08%` and recomputed from the pinned strata;
- comparison: rural/high-overlap tracts below that drought threshold.

The released preflight recorded `n=85` high-drought and `n=288` lower-drought tracts. Match on RUCA density, population, and SVI before comparing coverage. This triple interaction is not visible in the organizer's separate tribal, rural, and hazard slices. Apply the same raw-evidence, missingness, bootstrap, and falsification rules as the primary analysis.

## Reserve only: observation-distance interactions

Two additional preflight candidates remain reserves and must not be promoted unless their confounding checks pass:

- South-Central Texas: high SVI × high heat-stress change × far weather-station distance. The recorded far/near groups (`73/287`) differ materially in urban fraction, so a raw comparison is invalid.
- Northern California: high SVI × high wildfire hazard × far weather-station distance. Recorded cohorts are only `18/7`; treat this as exploratory and avoid a prize narrative unless the effect is unusually stable and source-backed.

## Reproducible execution contract

### Required inputs

Create `input-manifest.json` containing:

- exact repository/blob or object checksum for every organizer-provided file;
- exact scored sample checksum and row count;
- Overture release identifier;
- column mapping for GEOID, boundary type, rural/urban class, RUCA density, population, SVI, drought, heat, wildfire, station distance, and tribal overlap;
- extraction version and fixed random seed.

Abort if a required column is missing, GEOID membership differs from the current sample, checksums drift after cohort freeze, or any removed/reference-equivalent source appears.

### Output tables

Write these public-safe artifacts:

1. `cohort-audit.csv`: GEOID, cohort, all matching covariates, match status, exclusion reason.
2. `coverage-evidence.csv`: GEOID, raw permitted evidence families, provider shares, missingness flags, provenance IDs.
3. `matched-effects.csv`: outcome, treated n, matched n, mean/median difference, 95% bootstrap interval, leave-one-out minimum/maximum, promotion-rule status.
4. `provenance.json`: feature-to-source paths, checksums, release IDs, extraction expressions, row counts.
5. `writeup.md`: plain-language question, method, evidence, uncertainty, limitations, and falsification result.

Sort every CSV by GEOID and serialize numeric values with a fixed precision. Re-running the same manifest must produce identical cohort membership, match links, and output hashes.

## Writeup language guard

Before real execution, describe every item as a **hypothesis**, **candidate**, or **plan**. After execution, distinguish:

- organizer-provided cohort facts;
- directly measured permitted Overture evidence;
- model-derived coverage summaries;
- public contextual narrative data, if any.

Do not describe association as causation, generalize beyond the four scored regions, or claim a disparity when the promotion rule fails. Include null and adverse findings in the final package.

## Current money and action state

- Award advertised for this special-prize lane: **$1,000**.
- Proposed: $0.
- Promised: $0.
- Funded to this lane: $0 verified.
- Awarded: $0.
- Invoiced: $0.
- Received: $0.
- Zindi account/join/rules acceptance/submission: not performed by this artifact.

Next authorized data seat: pin the live organizer inputs, run this plan once, and attach the five exact output artifacts and hashes to the single authenticated Zindi submission owner.
