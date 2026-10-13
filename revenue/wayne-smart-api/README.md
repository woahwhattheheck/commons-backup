# Wayne RESA SMART API reconciliation (synthetic shadow)

Task: `wayne-smart-api-01`

This package is a deterministic **synthetic, read-only** reconciliation shadow for the posted Wayne RESA SMART API build demand. It does not connect to a Wayne RESA, SMART, student, provider, customer, financial, or production system and performs no authoritative mutation.

## Frozen 150-state contract

`fixtures/wayne_150_states.json` deterministically expands to 150 synthetic reconciliation states:

- 120 `RECONCILED` authorized known commits.
- 10 `DUPLICATE_NOOP` duplicate mutation attempts.
- 10 `HOLD_UNKNOWN_COMMIT` unknown commit IDs.
- 10 `HOLD_UNAUTHORIZED` unauthorized synthetic principals.

PASS requires all 150 to match the frozen truth set, **zero duplicate mutation effects**, **$0.00 ledger variance**, **zero unauthorized protected reads/effects**, every unknown commit held before protected read, no forbidden identity-shaped fields, and no change to the copied authoritative-state fingerprint. Replaying all 150 states against the same shadow adds zero staged effects, holds, events, or protected reads.

The fixture and expanded record set are SHA-256 pinned by a content-envelope manifest. Only synthetic `synthetic://` source URIs are accepted.

## Run

```bash
python revenue/wayne-smart-api/test_wayne_smart_reconcile.py
python -m py_compile revenue/wayne-smart-api/wayne_smart_reconcile.py revenue/wayne-smart-api/test_wayne_smart_reconcile.py
python revenue/wayne-smart-api/wayne_smart_reconcile.py
```

No external writes, outreach, presale transport, payment/spend, student/customer data, or automatic action are part of this artifact.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
