# Best Bias Discovery work order

This track is deliberately separated from the scored submission pipeline.

## Goal

Find one defensible, reproducible bias pattern in where Overture coverage gaps are concentrated and explain the mechanism without feeding extra data into the scored `coverage_gap_score`.

## Predeclared analysis

Use only the organizer-computed per-tract diagnostics plus challenge-provided contextual strata for the primary discovery pass. Rank candidate findings by:

1. effect size and uncertainty rather than p-value alone;
2. replication across more than one study region where the same construct exists;
3. stability when tracts with undefined components are excluded rather than imputed;
4. stability under population / land-area / urbanicity strata supplied by the challenge;
5. a mechanism that distinguishes map-source omission from denominator artifacts.

Candidate examples to test, not conclusions:

- building undercoverage concentrating in rural / large-area tracts;
- transport completeness differing across urbanicity strata after reference-road volume is controlled;
- facility POI gaps being dominated by one facility class rather than general establishment sparsity;
- component disagreement: tracts with strong roads/buildings but weak POIs, or the reverse.

## Extra public data rule

The challenge permits additional public data for the Best Bias Discovery writeup but not for the scored computation. Any enrichment must live in a separate analysis artifact with source URL, license, retrieval time, exact join key, missingness accounting, and a statement that the enrichment never entered the scorer.

## Required artifact

Produce a short reproducible notebook/script + machine-readable result table containing:

- hypothesis fixed before enrichment;
- tract inclusion/exclusion counts;
- undefined-component counts;
- effect estimates and uncertainty;
- regional replication table;
- robustness checks;
- exact source/version identities;
- limitations and plausible denominator/measurement confounds.

No demographic or geographic group should be described as intrinsically deficient. Findings are about **mapping/data coverage and measurement systems**, not about the people living in a tract.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
