# Methods-ready note

## Objective

Prepare a deterministic, data-free validation layer for a 12-label knee-MRI classification submission without copying restricted competition data into the repository.

## Public evaluation contract

The public competition page specifies macro-averaged ROC AUC: each of the twelve label AUCs contributes equally. The public submission schema has one `StudyInstanceUID` plus twelve confidence-score columns.

## Validation design

1. Parse CSV with the Python standard library.
2. Require the exact public header and ordering.
3. Require one unique, non-empty study identifier per row.
4. Convert every target value to a finite float in `[0, 1]`.
5. Optionally reconcile the submission's identifier set against a local authorized `test.csv`.
6. Compute local binary ROC AUC using the Mann–Whitney rank statistic with average ranks for ties.
7. Average target AUCs equally across the twelve labels.
8. Fail measured notebook runtimes above the public 9-hour ceiling.

## Reproducibility

The implementation has no third-party runtime dependencies. The focused test suite uses synthetic IDs, labels, and probabilities only and covers valid output, column order, duplicate IDs, probability bounds, ID-set mismatch, AUC ties, single-class failure, all-target macro averaging, and runtime boundaries.

## Explicit non-claims

No competition data was downloaded or redistributed for this readiness layer. No Kaggle entry, notebook submission, leaderboard score, efficiency score, rank, award, clinical claim, or payout is represented by these files.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

