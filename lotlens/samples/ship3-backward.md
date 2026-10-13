# LotLens impact report — pilot-plant/shipment/SHIP-3 (backward)

Generated 2026-09-05T12:11:33.853711Z · content sha256 `c85c908291338ca63f2041cf6b0774f7f2c430953abb9963e5b396539bad46fe`
Imports: `93948a1e5f015bad` (pilot)
Assumptions in force: none

8 known affected · 0 potentially affected · 0 unresolved · 0 coverage gaps · 0 contradictions

| status | item | kind | what | hops | via | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| KNOWN_AFFECTED | `pilot-plant/batch/BATCH-P1` | batch | RTD-LEMON | 3 | shipped → packed → consumed | shipments.csv:4; packages.csv:4; consumption.csv:4 |
| KNOWN_AFFECTED | `pilot-plant/batch/BATCH-P2` | batch | RTD-LEMON | 2 | shipped → packed | shipments.csv:4; packages.csv:4 |
| KNOWN_AFFECTED | `pilot-plant/package/PKG-P2-2` | package | RTD-LEMON | 1 | shipped | shipments.csv:4 |
| KNOWN_AFFECTED | `sup-acme/lot/LOT-CITRIC-01` | lot | citric acid Acme Acids | 5 | shipped → packed → consumed → consumed → split | shipments.csv:4; packages.csv:4; consumption.csv:4; consumption.csv:2; splits.csv:2 |
| KNOWN_AFFECTED | `sup-acme/lot/LOT-CITRIC-01A` | lot | citric acid Acme Acids | 4 | shipped → packed → consumed → consumed | shipments.csv:4; packages.csv:4; consumption.csv:4; consumption.csv:2 |
| KNOWN_AFFECTED | `sup-acme/lot/LOT-SUGAR-02` | lot | cane sugar Acme Sweet | 3 | shipped → packed → consumed | shipments.csv:4; packages.csv:4; consumption.csv:5 |
| KNOWN_AFFECTED | `sup-aqua/lot/LOT-WATER-01` | lot | process water Aqua Ltd | 3 | shipped → packed → consumed | shipments.csv:4; packages.csv:4; consumption.csv:6 |
| KNOWN_AFFECTED | `sup-h2o/lot/LOT-WATER-01` | lot | process water H2O Co | 4 | shipped → packed → consumed → consumed | shipments.csv:4; packages.csv:4; consumption.csv:4; consumption.csv:3 |

`*` marks an edge that exists only under a named assumption.

## Unresolved

none recorded

## Coverage gaps

none recorded

## Contradictions

none recorded

## Cycles

none recorded

## Investigator annotations

none

KNOWN_AFFECTED has a documented row path; POTENTIALLY_AFFECTED needs the named assumption; a coverage gap means the records stop there, not that nothing happened after it.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
