# Rhode Island Foundation Community Priority Grant-to-Outcome Evidence Rail — delivery core

This directory is an **offline, synthetic acceptance core** for the post-award workflow described in the 2026-09-13 commercial offer. It is not buyer acceptance, production deployment, a grant-selection engine, a payment rail, compliance certification, or an impact-scoring system.

## What it reconciles

`rail.py` accepts an approved event set containing awards, versioned restrictions/amendments, disbursements, milestones, evidence hashes, and returns. It emits one canonical manifest with exact-cent net-disbursement totals by program, priority, fund, and grantee; complete authorization lineage; named human-review holds; and a content-addressed offline receipt.

The core is deliberately fail-closed: unknown references, conflicting identifiers, invalid money types, non-contiguous amendment versions, over-disbursement, over-return, malformed evidence hashes, schema drift, or beneficiary-PII fields stop reconciliation. Byte-identical retry events are collapsed so retries do not create duplicate state. Input order does not affect output bytes.

## Authority boundary

The manifest hard-codes all four authority flags to `false`. This package does **not** select grantees, score applications or causal impact, initiate or approve disbursements, certify compliance, contact grantees, or ingest beneficiary PII. Buyer-approved definitions, integrations, identity/RBAC, data-retention policy, real evidence, deployment controls, and signed acceptance remain outside this synthetic core.

## Acceptance fixture

`fixtures/acceptance.json` spans both programs and all five priorities, includes a versioned award amendment, six disbursements, one return, evidence, and one intentionally overdue milestone. Expected net disbursement is **43,750,000 cents** and the overdue milestone is routed to `Foundation grant operations reviewer`.

Run:

```bash
python3 -m unittest revenue/rif_community_priority_grant_outcome_rail/test_rail.py -v
python3 -O -m unittest revenue/rif_community_priority_grant_outcome_rail/test_rail.py -v
python3 revenue/rif_community_priority_grant_outcome_rail/rail.py build \
  revenue/rif_community_priority_grant_outcome_rail/fixtures/acceptance.json \
  --manifest /tmp/rif-manifest.json --receipt /tmp/rif-receipt.json
python3 revenue/rif_community_priority_grant_outcome_rail/rail.py verify /tmp/rif-manifest.json /tmp/rif-receipt.json
```

Two clean builds of the same logical event set must produce byte-identical manifests and receipts. The verifier rejects a modified manifest even when the old receipt is supplied.
