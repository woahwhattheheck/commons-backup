# Fleet work order synthetic receipt

Status: `WORKING_SYNTHETIC_DEMO`

Fixture `inspection-1042` proves the public engine's binary contract:

- ordinary processing creates one deterministic work-order id and one deterministic escalation id;
- replay returns `REPLAY_NOOP` and preserves the same receipt;
- crashes after prepare and after effect persistence resume to exactly one of each effect;
- incomplete work can remove provisional effects and records `ROLLED_BACK`;
- same id with different normalized bytes returns `CONFLICT`;
- invalid input creates zero effects.

Test command: `node test_fleet_work_order.js`

Expected result: `fleet-work-order: 7 scenarios PASS`.

Limits: synthetic/browser-local proof only. It does not establish a production fleet connector, dispatch, buyer delivery, payment, settlement, payout, or cash. Entry offer is $199 for one business day; $2,500 proof follows only after a buyer-approved fit.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

