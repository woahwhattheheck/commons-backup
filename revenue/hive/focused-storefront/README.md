# Focused Storefront — demand 033

A dependency-free local commerce control plane for `bm-hive-20260908-033`. It is designed to bind a narrow product listing to documented supplier/sample evidence, explicit unit economics, inventory, fulfillment handoff, support terms, and a durable return workflow.

## Truth boundary

The included fixture is intentionally **synthetic**. `Fixture Supply Co.` is fictional and `media/synthetic-cable-clip.svg` is a self-authored illustration, not a photograph of a physical sample. The fixture therefore keeps `supplier_verified`, `sample_verified`, `real_test_order_completed`, `real_test_return_completed`, `external_checkout_enabled`, and `ready_for_real_sales` false. Replace the fixture with authorized evidence and complete the physical supplier/sample/order/return checks before representing the storefront as ready for real sales.

This package never places a supplier order, charges a customer, issues a refund, buys shipping, sends a message, or mutates a provider account.

## Run

```sh
cd revenue/hive/focused-storefront
python3 storefront.py --db ./workspace.sqlite3 init
python3 storefront.py --db ./workspace.sqlite3 serve --port 8097
```

Open `http://127.0.0.1:8097`. The page offers a **local synthetic** order → fulfillment → return → restock rehearsal and exports JSON plus a CSV fulfillment handoff.

Run tests:

```sh
python3 -B -m unittest -v test_storefront.py
```

## Supplier/product fixture contract

`examples/synthetic-supplier.json` records supplier identity/source reference, explicit verification flags, one product/SKU, economics, shipping/support terms, starting stock, and relative media paths. On database creation the exact fixture SHA-256 and media SHA-256 are stored/returned. Reopening an existing database with a different fixture hash is rejected rather than silently changing commercial facts.

Unit contribution is modeled as:

`price - landed cost - rounded-up channel fee - return reserve - support allowance`.

That is a planning value, not realized profit. Taxes, overhead, ad spend, chargebacks, payment timing, supplier minimums, and actual return rates are not inferred.

## Durable workflow

- Orders reserve stock atomically and use a unique idempotency key.
- Fulfillment consumes both on-hand and reserved units exactly once.
- A fulfilled order can create at most one return request; repeated delivery of the same request returns the existing record.
- Completing a return records the restock decision exactly once. A completed decision cannot be silently changed.
- The ledger exposes stock deltas and references for reconstruction.
- JSON export contains the fixture/gates, unit economics, inventory, orders, returns, and ledger. CSV handoff contains order state and modeled contribution.
- The HTTP server uses the same `Store` methods as the CLI/test harness; no external commerce API is implied.

## Real acceptance still open

Before any real storefront/customer use: document the supplier and shipping/return terms, receive and inspect an authorized physical sample against listing/media, reconcile real landed costs/fees, execute a controlled test order and return through the chosen supplier workflow, and record the observed results. Those gates are deliberately not marked complete by this repository build.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
