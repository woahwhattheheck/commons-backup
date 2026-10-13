# Pursuit Evidence Bridge

This package closes the gap between opportunity-specific pursuit carriers and the shared `revenue.bidder_qualification_vault` without letting one runtime packet mint its own trust roots.

A pursuit becomes `OPPORTUNITY_EVIDENCE_READY` only when all of these are true at the process-owned current UTC time:

1. the selected binding already exists in the checked-in `bindings.json` registry;
2. the exact canonical JSON bytes of the opportunity source ledger and submission manifest match the SHA-256 roots pinned by that binding;
3. the process-owned clock is before the binding's repo-reviewed proposal deadline;
4. the binding has no repo-reviewed static HOLD reason;
5. the binding pins authority, registry, and query SHA-256 roots for the existing bidder-qualification vault; and
6. `verify_bundle(...)` reconstructs the historical vault bundle and re-evaluates the same pinned evidence as currently `EVIDENCE_READY`.

The CLI does **not** accept `as_of`, deadline, expected source hash, expected manifest hash, expected vault roots, or an alternate binding registry from stdin. Those values must move through an ordinary repository change before they can influence readiness. This prevents the caller-self-authentication pattern where one JSON packet supplies both the claim and the value that supposedly proves it.

The supported `compile_bridge(...)` CURRENT path also binds its process clock and time-normalization/evaluation capabilities at module initialization. Ordinary importer rebinding of the corresponding `bridge` module globals (`datetime`, `timezone`, `_process_now`, timestamp helpers, or `_evaluate_at`) therefore cannot retarget current evaluation after import. This boundary does not claim protection from a trusted process owner deliberately rewriting function code, defaults, or closure cells.

`OPPORTUNITY_EVIDENCE_READY` is still evidence readiness only. Every action-authority flag is false and `external_submission_authorized` is always false. The bridge never authorizes buyer/reference contact, portal mutation, submission, signing, certification or insurance claims, pricing/staffing commitments, contract acceptance, spend, award, payment, or revenue recognition.

## Current production binding

`jersey-dn827803-main-v1` binds the already-landed States of Jersey DN827803 carrier on Commons main:

- source ledger: `opportunities/jersey_connecting_health_cdr_openehr_dn827803/sources.json`;
- manifest: `opportunities/jersey_connecting_health_cdr_openehr_dn827803/fixtures/public_hold.json`;
- deadline: `2026-09-29T22:30:00Z` (the checked-in public listing's `2026-09-29T23:30:00+01:00` normalized to UTC);
- static HOLD: controlling tender pack is not acquired or reviewed; and
- bidder-vault roots: intentionally unpinned, so runtime evidence cannot upgrade the carrier by self-supplying roots.

That binding therefore remains truthful `HOLD`. A later source owner can update the carrier and binding in one reviewed change when controlling bytes and independently retained bidder-evidence roots exist.

## CLI

```bash
python -m revenue.pursuit_evidence_bridge.bridge jersey-dn827803-main-v1 < envelope.json
```

Envelope shape is exact:

```json
{
  "source_ledger": {},
  "submission_manifest": {},
  "vault": null
}
```

When a binding has pinned vault roots, `vault` must instead contain exactly `authority`, `registry`, `query`, and `bundle` from the existing bidder-qualification vault. Exit status is `0` for `OPPORTUNITY_EVIDENCE_READY`, `2` for a valid current `HOLD`, and `3` for malformed, unbound, root-mismatched, or tampered input.

## Adding or rotating a binding

A source owner updates `bindings.json` alongside the opportunity bytes. Pin canonical-JSON SHA-256 roots for the source ledger and submission manifest. For a positive evidence path, pin all three vault roots together: authority, registry, and the exact query. Never copy roots out of the runtime envelope being evaluated; the point of the registry is that trust is retained outside that envelope. Static HOLDs describe known source-side blockers that evidence cannot override.

## Validation

```bash
python -m unittest -v revenue.pursuit_evidence_bridge.test_bridge revenue.pursuit_evidence_bridge.test_current_clock_custody
python -O -m unittest -v revenue.pursuit_evidence_bridge.test_bridge revenue.pursuit_evidence_bridge.test_current_clock_custody
python -m py_compile revenue/pursuit_evidence_bridge/*.py
```

The hostile suite covers pinned production-byte drift, duplicate/extra input keys, source/manifest root mismatch, process-owned deadline expiry, all-or-none vault roots, query transplant, current-vault HOLD propagation, positive vault integration, ordinary module-global current-clock rebinding, and the invariant that every action-authority bit remains false.