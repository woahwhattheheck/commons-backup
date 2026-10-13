# Checkout inventory

This lane is a **read-only provider census**, not a sales ledger and not a Stripe writer. It captures the active Token Junkie Labs Payment Link surface returned by authenticated live-mode Stripe reads, binds each link to its provider product/price, reconciles the original seven Commons SKU URLs against the existing canonical table, and emits duplicate/unkeyed cleanup review without authorizing deactivation.

## 2026-09-18 retained snapshot

The retained provider readback contains:

- 36 active Payment Links;
- 32 links with an offer/SKU metadata key and 4 unkeyed links;
- 4 manual-capture links;
- 4 subscriptions;
- 23 single-use links with zero completed sessions;
- 0 PaymentIntents returned by the current limit=100 account query; and
- 0 balance transactions returned by the current limit=100 account query.

Those last two facts describe this Stripe snapshot only. They do **not** establish global revenue, bank settlement, buyer acceptance, or the absence of money on another provider.

The old Commons SKU catalog still has exactly one active provider match for each of its seven canonical URLs. Two keys also have active older duplicates:

- sku-tip-20260826: three active links; the existing canonical URL is the $5 donation link. The other active variants are $1 and $5.
- sku-unlock-20260826: two active links; the existing canonical URL is $5. The other active variant is $9.

A fresh compiler run exposes the three noncanonical links as **review-only** cleanup candidates. Nothing in this package authorizes a Stripe mutation or link deactivation.

## Recompile and verify

Run:

    d=$(mktemp -d)
    python host/checkout_inventory.py compile \
      revenue/checkout_inventory/provider_snapshot.json \
      land/stripe-payment-links-20260826.md \
      --output "$d/report.json"

    python host/checkout_inventory.py verify \
      revenue/checkout_inventory/provider_snapshot.json \
      land/stripe-payment-links-20260826.md \
      "$d/report.json"

    python -m unittest -v test_checkout_inventory.py
    python -O -m unittest -v test_checkout_inventory.py

## Refresh protocol

1. Read the live Stripe account using authenticated provider tools.
2. List active Payment Links and fetch each link's complete line items with product expansion.
3. Separately read PaymentIntents and balance transactions.
4. Retain only the bounded non-secret fields represented by provider_snapshot.json.
5. Run the normal and optimized test suites and compile a fresh report.
6. Review duplicate/unkeyed findings before any separate provider mutation. A provider write requires its own authority and provider-state fence.

The repository snapshot is historical evidence after capture; it does not remain current merely because its file still validates.
