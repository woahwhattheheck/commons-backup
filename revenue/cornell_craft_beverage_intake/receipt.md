# cornell-craft-beverage-intake-lims-01 receipt

State: TESTED
Binary: `python3 test_cornell_craft_beverage_intake.py` → 9/9 OK
CLI: `python3 cornell_craft_beverage_intake.py` → ok true, failures []

| check | value |
|---|---|
| input rows | 8 |
| accessioned once | 6 |
| rejected | 2 |
| reject codes | MISSING_SAMPLE_ID, UNDER_VOLUME |
| CCB-W01 route | WINE_MULTI |
| CCB-W02 route | WINE_SINGLE |
| CCB-S01 route | SPIRITS_ABV |
| CCB-K01 route | KOMBUCHA_ABV |
| CCB-J01 route | JUICE_PANEL |
| CCB-C01 route | CIDER_SINGLE |
| frozen juice RECEIVED | both flags required |
| reports released | 0 |
| replay added accessions | 0 |
| manifest_sha256 | db474eb72912a2ce972178ebef3c91db4e6549b2823b80c574d17c30417f1080 |

Interfaces simulated. No autonomous certification or release. AquaTrace HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

