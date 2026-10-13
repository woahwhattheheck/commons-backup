# Accepted-scope-to-delivery

This directory is the machine-readable composition layer that turns a **written
buyer agreement** into the artifacts a real delivery needs:

1. exact statement of work
2. bounded work packet
3. execution status
4. evidence bundle
5. delivery receipt
6. invoice / payment state
7. buyer-readable handoff

It composes the existing Outcome Commerce catalog, production-survival
acceptance lock, DIO delivery-receipt rule, checkout handoff money states, and
human-outcomes SKUs. It does **not** replace those roads.

## Honesty

- Do not fake acceptance, work, delivery, invoice, payment, testimonial, or receipt.
- `ACCEPTED` requires `written_acceptance.status = PRESENT`, the exact terms
  digest, a catalog SKU, and a catalog-matching amount.
- `LOCKED_SOW` exists only after `ACCEPTED`. Party names, emails, and addresses
  stay `NOT_ON_PUBLIC_MAIN`.
- A work packet is issued only from a locked SOW.
- `PASS` requires every binary acceptance row `PASS` with `public_ref` + `sha256`.
- `delivered` is true only on `PASS`. Payment never proves delivery.
- `QUOTED != CHARGEABLE != INVOICED != AUTHORIZATION != SETTLEMENT != PAYOUT != BANK_AVAILABLE`.
- `cash_claimed` is true only at `BANK_AVAILABLE`.
- Current catalog funnel truth remains `accepted_scopes: 0`, `paid_deliveries: 0`,
  `collected_cash_usd: "0.00"` until live evidence says otherwise. Fixtures here
  are synthetic and public.

## Trusted-time prerequisite

The v1 composer is a deterministic content projection; it does not by itself
establish that a historically accepted scope is still inside its work window.
Before beginning current work from `LOCKED_SOW` / `ISSUED`, require a fresh
`host/scope_to_delivery_time_gate.py` result with
`current_work_authorized=true` **and** the canonical composer validation.

The temporal gate uses verifier-controlled UTC, constrains every observation to
the accepted contract window, rejects future evidence, and returns
`HOLD_WINDOW_EXPIRED` after the window closes. A completed historical delivery
can remain auditable without reopening work authority. See
[`TRUSTED_TIME_GATE.md`](./TRUSTED_TIME_GATE.md).

## CLI

```text
python3 host/scope_to_delivery.py catalog
python3 host/scope_to_delivery.py sow --agreement revenue/scope_to_delivery/fixtures/accepted_agreement.json
python3 host/scope_to_delivery.py project \
  --agreement revenue/scope_to_delivery/fixtures/accepted_agreement.json \
  --observations revenue/scope_to_delivery/fixtures/accepted_observations.json \
  --payment revenue/scope_to_delivery/fixtures/payment_authorized.json

# Current-work temporal prerequisite (uses process UTC; no caller as-of override)
python3 host/scope_to_delivery_time_gate.py \
  --agreement revenue/scope_to_delivery/fixtures/accepted_agreement.json \
  --observations revenue/scope_to_delivery/fixtures/accepted_observations.json
```

Stdlib only. No Stripe, Airtable, email, or bank calls.

## Surfaces

- Human door: [`../../scope-to-delivery.html`](../../scope-to-delivery.html)
- Ground: [`../../ground/SCOPE_TO_DELIVERY.md`](../../ground/SCOPE_TO_DELIVERY.md)
- Host: [`../../host/scope_to_delivery.py`](../../host/scope_to_delivery.py)
- Temporal gate: [`../../host/scope_to_delivery_time_gate.py`](../../host/scope_to_delivery_time_gate.py)
- Tests: [`../../test_scope_to_delivery.py`](../../test_scope_to_delivery.py)
- Temporal tests: [`../../test_scope_to_delivery_time_gate.py`](../../test_scope_to_delivery_time_gate.py)
- Bindings: [`catalog_bindings.json`](./catalog_bindings.json)
- Synthetic fixtures: [`fixtures/`](./fixtures/)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
