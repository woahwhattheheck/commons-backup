# Big Onion 48-hour hold-rescue queue

Demand: `big-onion-hold-rescue-01`

This is a **synthetic, read-only** queue evaluator. It identifies unresolved synthetic queue events that have been explicitly labeled `UNPAID` or `FAILED_DEPOSIT` for at least 48 hours and returns operator-review recommendations. It does not contact anyone, retry a payment, send a reminder, collect funds, or mutate a provider/customer/system record.

## Frozen acceptance

The checked-in fixture contains exactly six synthetic events. With `as_of=2026-09-09T12:00:00Z` and the pinned 48-hour cutoff:

- `E1` (`UNPAID`, 72h) is eligible.
- `E2` (`FAILED_DEPOSIT`, exactly 48h) is eligible.
- `E3` is too young.
- `E4` is already resolved.
- `E5` is not in an eligible state.
- `E6` is malformed and fails closed.

The only recommendation IDs are therefore **`E1,E2` in source order**. A full replay is byte-for-byte equivalent at the result level and adds no state/events. Every result reports `sends=0`, `actions=0`, `provider_writes=0`, `state_mutations=0`, and `events_added=0`.

The fixture is hash-bound to `fixtures/manifest.json`; the manifest also pins the schema/version, `as_of`, 48-hour cutoff, eligible state names, and expected IDs. Sensitive/customer/payment-shaped fields fail closed rather than entering the queue output.

## Run

```bash
python -m unittest -v test_big_onion_hold_rescue.py
python -m py_compile big_onion_hold_rescue.py test_big_onion_hold_rescue.py
python big_onion_hold_rescue.py
```

## Boundary

Synthetic fixtures only. No real customer or payment data, no outreach, no reminders or collections, no payment/provider/customer/system write, no transport, no spend, and no autonomous action. `HUMAN_REVIEW_ONLY` is a recommendation label, not a send or collection instruction.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

