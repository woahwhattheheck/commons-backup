# Product lifecycle tombstone

This directory is the machine-readable lifecycle boundary for customer-facing products that can appear on Commons active checkout/storefront surfaces.

`registry.json` is descriptive lifecycle state. It does **not** grant Stripe/provider mutation, payment, refund, invoice, customer-contact, payout, cash, accounting, or revenue-recognition authority.

## States

- `ACTIVE` — the product may appear on active surfaces.
- `RETIRING` — cleanup is in flight. The guard deliberately does not block yet so one retirement carrier can remove the active footprint without making current `main` permanently red.
- `RETIRED` — the recorded checkout identities and active catalog/source files are tombstoned and may not reappear.

A retirement must compose the last active-footprint/source removal and the `RETIRING -> RETIRED` flip in the same semantic generation. From that point forward, a PR is checked against the trusted base-branch lifecycle generation: a product already `RETIRED` there cannot be deleted, downgraded, or stripped of any checkout/catalog identity by the candidate. The candidate therefore cannot erase the tombstone before resurrecting a stale shelf.

## Active vs historical

`host/product_lifecycle_guard.py` scans active root `*.html` customer surfaces plus the active payment-capability and outcome-commerce catalog sources. Root `board.html` is the live projection of historical board receipts, not a customer storefront, and is excluded with `p/`, `by/`, and `d/`. Every lifecycle `catalog_sources` path is also direct active source state: once its product is `RETIRED`, that source path itself must be absent. Historical `p/`, `by/`, `d/`, and other append-only evidence trees are intentionally not recursively scanned or rewritten. Historical receipts remain evidence; retirement is not history deletion.

Every lifecycle `catalog_sources` path must have an exact path trigger in the retained `.github/workflows/capability-entrypoints.yml` workflow. This makes a stale restoration wake the guard even if no already-active surface changed in the same commit.

## Checkout identity

Registry-controlled checkout URLs are strict HTTPS identities without credentials, query strings, fragments, or non-default ports. Active-surface matching is intentionally more hostile: equivalent HTTP/protocol-relative spellings, DNS trailing dots, percent-encoded path aliases, trailing slashes, query strings, and fragments are reduced to the protected scheme/host/path identity. An ambiguous checkout-looking URL on a retired checkout host fails closed rather than disappearing from the scan.

## Local proof

```bash
python -m py_compile host/product_lifecycle_guard.py revenue/product_lifecycle/test_guard.py
python -m unittest -v revenue.product_lifecycle.test_guard
python -O -m unittest -v revenue.product_lifecycle.test_guard
python host/product_lifecycle_guard.py --repo-root . --base-registry /path/to/trusted-base-registry.json
python -O host/product_lifecycle_guard.py --repo-root . --base-registry /path/to/trusted-base-registry.json
```

On pull requests, the retained `capability-entrypoints` workflow materializes the registry from the GitHub-controlled base branch after verifying the base ref. On pushes/workflow dispatch it uses the first parent. If the trusted generation predates this lifecycle source, the workflow supplies the strict empty v1 registry as the one-time bootstrap base; it does not silently substitute empty state when the trusted Git ref itself is missing.
