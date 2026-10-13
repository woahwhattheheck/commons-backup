# LotLens impact report — sup-acme/lot/LOT-CITRIC-01 (forward)

Generated 2026-09-05T12:11:33.631547Z · content sha256 `a29f7efbb563dec04890c9fb7f1633950c27af79e0dde4689626e89b97c8be24`
Imports: `93948a1e5f015bad` (pilot)
Assumptions in force: none

16 known affected · 0 potentially affected · 1 unresolved · 1 coverage gaps · 2 contradictions

| status | item | kind | what | hops | via | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| KNOWN_AFFECTED | `pilot-plant/batch/BATCH-P1` | batch | RTD-LEMON | 2 | split → consumed | splits.csv:2; consumption.csv:2 |
| KNOWN_AFFECTED | `pilot-plant/batch/BATCH-P2` | batch | RTD-LEMON | 3 | split → consumed → consumed | splits.csv:2; consumption.csv:2; consumption.csv:4 |
| KNOWN_AFFECTED | `pilot-plant/batch/BATCH-P3` | batch | RTD-LIME | 2 | split → consumed | splits.csv:3; consumption.csv:7 |
| KNOWN_AFFECTED | `pilot-plant/batch/BATCH-P4` | batch | RTD-LEMON | 4 | split → consumed → consumed → rework | splits.csv:2; consumption.csv:2; consumption.csv:4; rework.csv:2 |
| KNOWN_AFFECTED | `pilot-plant/package/PKG-P1-1` | package | RTD-LEMON | 3 | split → consumed → packed | splits.csv:2; consumption.csv:2; packages.csv:2 |
| KNOWN_AFFECTED | `pilot-plant/package/PKG-P2-1` | package | RTD-LEMON | 4 | split → consumed → consumed → packed | splits.csv:2; consumption.csv:2; consumption.csv:4; packages.csv:3 |
| KNOWN_AFFECTED | `pilot-plant/package/PKG-P2-2` | package | RTD-LEMON | 4 | split → consumed → consumed → packed | splits.csv:2; consumption.csv:2; consumption.csv:4; packages.csv:4 |
| KNOWN_AFFECTED | `pilot-plant/package/PKG-P3-1` | package | RTD-LIME | 3 | split → consumed → packed | splits.csv:3; consumption.csv:7; packages.csv:5 |
| KNOWN_AFFECTED | `pilot-plant/package/PKG-P4-1` | package | RTD-LEMON | 5 | split → consumed → consumed → rework → packed | splits.csv:2; consumption.csv:2; consumption.csv:4; rework.csv:2; packages.csv:6 |
| KNOWN_AFFECTED | `pilot-plant/shipment/SHIP-1` | shipment | Cafe North | 4 | split → consumed → packed → shipped | splits.csv:2; consumption.csv:2; packages.csv:2; shipments.csv:2 |
| KNOWN_AFFECTED | `pilot-plant/shipment/SHIP-2` | shipment | Cafe North | 5 | split → consumed → consumed → packed → shipped | splits.csv:2; consumption.csv:2; consumption.csv:4; packages.csv:3; shipments.csv:3 |
| KNOWN_AFFECTED | `pilot-plant/shipment/SHIP-3` | shipment | Market South | 5 | split → consumed → consumed → packed → shipped | splits.csv:2; consumption.csv:2; consumption.csv:4; packages.csv:4; shipments.csv:4 |
| KNOWN_AFFECTED | `pilot-plant/shipment/SHIP-4` | shipment | Market South | 4 | split → consumed → packed → shipped | splits.csv:3; consumption.csv:7; packages.csv:5; shipments.csv:5 |
| KNOWN_AFFECTED | `pilot-plant/shipment/SHIP-9` | shipment | Deli East | 4 | split → consumed → packed → shipped | splits.csv:3; consumption.csv:7; packages.csv:5; shipments.csv:8 |
| KNOWN_AFFECTED | `sup-acme/lot/LOT-CITRIC-01A` | lot | citric acid Acme Acids | 1 | split | splits.csv:2 |
| KNOWN_AFFECTED | `sup-acme/lot/LOT-CITRIC-01B` | lot | citric acid Acme Acids | 1 | split | splits.csv:3 |

`*` marks an edge that exists only under a named assumption.

## Unresolved

- `consumed_input_not_in_records` on `pilot-plant/batch/BATCH-P4` — {"input_ref": "sup-acme/lot/LOT-VANILLA-09"} — consumption.csv:12

## Coverage gaps

- `package_without_shipment` on `pilot-plant/package/PKG-P4-1` — {} — packages.csv:6

## Contradictions

- `over_consumption` on `sup-acme/lot/LOT-CITRIC-01B`, `pilot-plant/batch/BATCH-P3` — {"consumed_total": 40.0, "lot_quantity": 30.0, "unit": "kg"} — consumption.csv:7; lots.csv:4
- `multiple_shipped_links` on `pilot-plant/shipment/SHIP-9`, `pilot-plant/package/PKG-P2-1`, `pilot-plant/package/PKG-P3-1` — {"count": 2, "relation": "shipped"} — shipments.csv:7; shipments.csv:8

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
