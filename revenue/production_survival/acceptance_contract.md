# Binary acceptance and capture lock

This operationalizes the already-published `same-day-agent-survival-proof`; it does not change its price, term, or ladder.

The public Stripe checkout collects the buyer's non-confidential failure sentence and asks Stripe to place a manual-capture USD 2,500 authorization. Checkout completion is not scope acceptance and does not capture the amount. Before capture, Bernays and the buyer write one binary test in this form:

> Given [public or synthetic input], when [named failure] is forced, the delivered proof [observable recovery outcome] and its receipt shows [named fields].

The written acceptance records the exact input, expected output, public-safe environment, `window_start`, `window_end`, and timezone. Acceptance is `PASS` only when a clean run produces the agreed outcome and receipt inside that window. Otherwise it is `MISS`; there is no subjective “mostly complete” state.

## Quote-to-clock path

1. The buyer starts from [`README.md`](./README.md) (operator entry for Same-Day Agent Survival Proof · $2,500) and uses the **buyer-specific** provider-hosted Payment Link / handoff issued for that scope — **not** `agent-rescue.html` (that page carried Agent Failure Autopsy · $29 only; retired with the SKU 2026-09-17). Enter the required non-confidential failure sentence and, optionally, one public evidence link.
2. Successful checkout creates a Stripe customer and attempts a USD 2,500 authorization with manual capture. It is not capture, settlement, payout, or cash.
3. Bernays returns the Given/When/Then test, delivery environment, exact America/New_York window, exclusions, fixed USD 2,500 price, and refund choice.
4. The buyer accepts those terms in writing before capture. If the scope is a bad fit or is not accepted, the authorization is canceled and no delivery clock starts.
5. For an accepted scope, the authorized amount is captured through Stripe. The delivery clock begins only at the agreed `window_start` after confirmed capture; a link open, checkout draft, pending event, or authorization alone does not start it.
6. If the exact binary test has not passed by `window_end`, the captured authorized amount is refunded unless the buyer elects in writing to receive one free next-business-day repair attempt instead.

The link has a one-completed-session limit so fulfillment stays one buyer at a time. After a completed checkout, do not reactivate it or mint a duplicate until that authorization is canceled or the accepted proof is delivered and capacity is explicitly available again.

The handoff includes:

- a source snapshot at an exact commit;
- the one-command clean-run instruction;
- dependency and runtime versions;
- the resulting receipt, its production-survival schema, and content hashes;
- a short walkthrough plus keep/change/stop recommendation.

The entry proof excludes credentials, private data, PII/PHI, authentication, billing, production migration, ongoing hosting or SLA, and all White Box/model-file work. Those exclusions are not silently traded for a shorter deadline.

`AUTHORIZATION != CAPTURE != SETTLEMENT != PAYOUT != BANK_AVAILABLE`. A public receipt may contain only the public link identifier or the permitted opaque processor reference and hash described in the existing processor handoff; it does not contain payment credentials or prove capture, settlement, payout, or bank availability.

The included synthetic example forces a timeout after an external effect but before the completion checkpoint. Recovery reuses an idempotency key, records a dedupe hit, and finishes with one external effect:

```text
python revenue/production_survival/survival_canary.py --intake revenue/production_survival/example_intake.json --state .survival-state.json --receipt .survival-receipt.json
```

The regression test reruns the completed operation and asserts that the receipt remains stable:

```text
python -m unittest revenue/production_survival/test_survival_canary.py
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
