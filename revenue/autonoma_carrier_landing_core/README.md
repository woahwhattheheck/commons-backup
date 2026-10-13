# Autonoma carrier-safe landing core

This is an **offline delivery core** for the commercial Autonoma offer sent on 2026-09-13. It turns bounded branch evidence into a deterministic, fail-closed landing receipt. It does not call GitHub, mutate repositories, send messages, operate customer systems, or claim buyer acceptance.

## What it proves

A batch is evaluated in declared order. A carrier can land only when all of these are true:

- its base SHA matches the batch base;
- every observed file is under the batch's carrier-only prefix;
- the observed file list exactly matches the declared manifest;
- the manifest digest matches the canonical manifest bytes;
- pre-merge and post-merge test evidence is PASS;
- its owned paths do not overlap an earlier admissible carrier.

Every hold is explicit. The current reason codes are `FORBIDDEN_PATH`, `STALE_BASE`, `MANIFEST_MISMATCH`, `TEST_FAILURE`, and `OWNERSHIP_COLLISION`.

The plan exposes only non-destructive `MERGE` intents. `force` and `delete_branch` are always false and are revalidated when a plan is consumed. Receipt bytes are deterministic and self-digested. Application is idempotent: once a receipt is in the completion state, applying that exact receipt again performs zero new merges and returns the identical receipt.

## Six-branch acceptance

Run from the repository root:

```bash
python -m revenue.autonoma_carrier_landing_core.acceptance
python -m unittest revenue.autonoma_carrier_landing_core.test_core
python -m py_compile \
  revenue/autonoma_carrier_landing_core/core.py \
  revenue/autonoma_carrier_landing_core/acceptance.py \
  revenue/autonoma_carrier_landing_core/test_core.py
```

The synthetic fixture contains exactly six carriers:

| Carrier | Expected result |
| --- | --- |
| `carrier-alpha` | LAND |
| `forbidden-path` | HOLD / `FORBIDDEN_PATH` |
| `stale-base` | HOLD / `STALE_BASE` |
| `manifest-mismatch` | HOLD / `MANIFEST_MISMATCH` |
| `test-failure` | HOLD / `TEST_FAILURE` |
| `carrier-omega` | LAND |

Acceptance also proves the two valid carriers land in declared order, main stays green after each simulated landing, no force-push or branch deletion intent is emitted, and replay of the completed batch performs zero new merges while reproducing the same receipt.

## Integration boundary

`core.py` is deliberately provider-free. A production adapter would be responsible for obtaining immutable GitHub evidence, running real tests, translating only verified `MERGE` intents into expected-head guarded provider calls, and recording provider receipts. That adapter must not treat this offline plan as proof that a live branch is still fresh or that CI is actually green.

This package is therefore suitable as a deterministic acceptance/reconciliation layer behind an Autonoma-style parallel-agent system, not as a credentialed merge bot by itself.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
