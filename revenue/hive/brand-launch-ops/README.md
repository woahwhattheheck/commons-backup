# Consumer Brand Launch Operations

A dependency-free operator workspace for `bm-hive-20260908-035`.

The product takes one operator-supplied SKU record and creates a consistent launch package for multiple sales channels: source-preserving listings, a creative brief, support drafts, reorder status, synchronized inventory handoff, and an order/return runbook. It also includes a local idempotent order → return state machine so a launch operator can exercise stock transitions before connecting a real commerce provider.

## What it does

- validates that the product facts required for launch were actually supplied;
- preserves SKU, price, currency, description, shipping terms, return window, attributes, benefits, and channel names rather than inventing missing facts;
- produces one channel listing per requested channel from the same canonical source;
- produces a creative brief constrained to supplied product facts and operator-provided claims;
- produces customer-support drafts and escalation boundaries;
- mirrors available stock across channel handoffs without publishing it anywhere;
- flags a reorder threshold but never places a supplier order;
- records order and return handoffs exactly once using caller-supplied IDs;
- rejects oversells and conflicting reuse of order/return IDs;
- emits a SHA-256 manifest for the generated launch package.

It does **not** publish a storefront, spend money, buy inventory, contact customers, move payment/refund funds, make health or safety claims, or infer product facts from photographs.

## Quick start

```bash
python revenue/hive/brand-launch-ops/launch_ops.py build \
  revenue/hive/brand-launch-ops/example_product.json \
  --out /tmp/brand-launch

python revenue/hive/brand-launch-ops/launch_ops.py order \
  --state /tmp/brand-launch/state.json \
  --order-id DEMO-001 --quantity 2

python revenue/hive/brand-launch-ops/launch_ops.py return \
  --state /tmp/brand-launch/state.json \
  --order-id DEMO-001 --return-id RET-001 --disposition restock
```

The `--out` directory must be new or empty of prior launch_ops artifacts (`state.json` / `manifest.json`). Re-running `build` against an existing managed workspace fails closed so that order/return state is never erased.

Generated output is intentionally local. A later provider adapter may consume `listings.json`, `inventory_handoff.json`, or the state transitions, but this package never treats local acceptance as a live sale or refund.

## Product input contract

`example_product.json` shows the required shape. Product attributes and benefits are operator-supplied facts; the tool will not fill missing claims. `creative_constraints` is optional. `channels` are simple operator-defined slugs so the same launch package can feed different approved provider adapters without encoding provider credentials here.

## Focused acceptance

```bash
python -m unittest discover -s revenue/hive/brand-launch-ops -p 'test_launch_ops.py' -v
```

Acceptance covers source-field preservation, claim restraint, manifest hashing, multi-channel stock consistency, CLI execution, oversell rejection, reorder threshold behavior, and idempotent order/return transitions.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
