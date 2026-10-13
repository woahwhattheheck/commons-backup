# Bid 1421 instrument fixtures (mock adapters)

Additive fixture pack for City of Billings Bid 1421 / AquaTrace lane 1.
Not product-core. Not a proposal. Not City contact. `cash_usd=0`.

Cite, do not remint: `aquatrace-lims-proof/` (owner-local synthetic proof; absent on public main).

## Source

Official RFP: https://www.billingsmt.gov/bids.aspx?bidID=1421
Document: https://www.billingsmt.gov/DocumentCenter/View/56340/2026-LIMS-RFP
SHA-256: `667d3d260f28877ad41ca6313d03eaddf3e45ae278a995ebf72d78d144339882`

Attachment F is the analysis list, the Instrumentation for Integration list, and Required Reporting. Section 3 points instrument integration at Attachment F.

## Layout

- `source.json` — measured RFP provenance
- `manifest.json` — normalized mock-adapter manifest
- `events.jsonl` — exactly 30 synthetic instrument events
- `expected_receipts.json` — deterministic receipts
- `runner.py` — in-memory mock ingest bus

Instrument-to-analyte wiring is `SYNTHETIC_BINDING`. Attachment F does not bind each instrument to an analyte.

## Scenarios (30)

| scenario | count | expected status |
| --- | --- | --- |
| normal_import | 12 | COMMITTED (10 named normal + 2 timeout first-half) |
| duplicate_delivery | 6 | DUPLICATE_SUPPRESSED, same commit_id, `commits_created=0` |
| out_of_order | 5 | HELD_OUT_OF_ORDER, not applied |
| bad_qc | 5 | FAIL_CLOSED, no commit, sequence does not advance |
| timeout_after_commit | 2 | TIMEOUT_AFTER_COMMIT, same commit_id, `commits_created=0` |

## Runner / test plan

```bash
python3 revenue/billings_bid_1421/instrument_fixtures/runner.py
python3 -m unittest -v test_billings_bid_1421_instrument_fixtures.py
```

PASS requires:

1. Exactly 30 events and 30 receipts.
2. Every receipt matches `expected_receipts.json`.
3. Duplicate delivery and timeout-after-commit never create a second commit.
4. Out-of-order events stay held; they are not silently applied.
5. Bad QC fails closed (no commit).
6. Unknown adapter/analyte is `FINDER UNVERIFIED` with a search space, never `0`.
7. Same-run calibration hits `mock-ph-meter-1` / analyte `pH`.
8. `cash_usd=0`. No Stripe. No secrets. No City send.

This is a mock-adapter fixture. It is not production, regulated, deployed, or instrument-connected.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
