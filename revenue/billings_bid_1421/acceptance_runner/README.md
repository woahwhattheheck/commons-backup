# AquaTrace Bid 1421 acceptance runner

In-process control rail that executes the existing 100-case AquaTrace
acceptance corpus (`AT-001`..`AT-100`). The corpus stays where it is.
This directory is the working program.

**State:** `HOLD / BUILD-AND-VERIFY` until a live golden round trip exists.
`cash_usd=0`. No City contact. No outreach. No autonomous regulatory release.

## Command

```bash
python3 revenue/billings_bid_1421/acceptance_runner/runner.py
python3 -m unittest test_billings_bid_1421_acceptance_runner.py
```

PASS requires 100/100 expected dispositions, one receipt per case, a
deterministic `audit_sha256`, replay byte-identity, and
`regulatory_release_count=0`.

## Cite, do not rewrite

- Corpus JSON Slack SHA-256 `355924d3e03dae5f2fb6759a927338a56d57ce1a9606897d65621256b340d313`
- Corpus receipt blob `054e321cef6226dc59ab2d6781f56637b3cb433d`
- Instrument fixtures receipt blob `03ff210c2385e5cbf9785e706d97c41b44689976`

## What the rail does

Field and offline collection, custody, laboratory receipt, QC / retest /
named-human release boundary, instrument ingest, audit export, report
reconciliation, role denial, and retry / recovery. Defects HOLD with an
exact reason. Retries never create a second business effect. A named
human is required before any regulatory release. This rail never
releases or transmits.

## Truth

Synthetic laboratory fixtures only. Not live-instrument compatible, not
a City submission, not certified, not production-deployed. Official RFP:
https://www.billingsmt.gov/bids.aspx?bidID=1421
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
