# Outbound Collision Replay Guard

A deterministic, provider-free single-writer control for outbound intents. This exists because search-then-send coordination is not atomic: two workers can both see "no prior sender" and race.

## Security boundary: authenticated Muse evidence

`READY_SINGLE_WRITER` is now reachable only through an HMAC-authenticated Muse registry. A caller-authored receipt mapping is **not** Muse authority and fails closed as `WAIT_MUSE`.

The verifier key is read only from the runtime secret `OUTBOUND_MUSE_TRUST_KEY`. The production module contains no signer and accepts no key from the untrusted registry. Tests and the offline demo create fixture signatures themselves; that fixture code is not exported by the package.

Registry schema: `outbound-collision-muse-registry/v1`.

```json
{
  "schema": "outbound-collision-muse-registry/v1",
  "generated_at": "2026-09-17T03:15:00Z",
  "receipts": [{
    "receipt_id": "muse-r1",
    "request_key": "muse-q1",
    "intent_fingerprint": "<sha256>",
    "selected_claimant_id": "seat-a",
    "selected_session_id": "session-a",
    "lease_generation": 1,
    "decision": "SELECTED",
    "arbitrated_at": "2026-09-17T03:14:59Z",
    "expires_at": "2026-09-17T03:25:00Z",
    "source_ref": "slack:dm:muse:...",
    "source_sha256": "<sha256>"
  }],
  "signature_hmac_sha256": "<HMAC-SHA256 over canonical body>"
}
```

The registry signature binds the exact receipt/request identity, selected claimant/session, lease generation, decision, timestamps, source reference, and source digest. Duplicate receipt IDs, source-evidence remints, future registries, registries that predate their arbitration evidence, expired/future receipts, conflicting selections, stale generations, source mutation, and wrong keys all fail closed.

A successful lease persists `muse_receipt_id`, `muse_request_key`, `muse_registry_sha256`, `muse_registry_generated_at`, `muse_source_ref`, and `muse_source_sha256`. This makes later send fencing auditable against the exact trusted registry bytes that created readiness.

## Compatibility

Intent fingerprint semantics remain compatible with the original v1 guard. Lease schema is v2 because authenticated Muse provenance is now part of the lease invariant.

- A legacy v1 `READY_SINGLE_WRITER` lease is rejected and must reacquire authenticated Muse evidence before a send attempt.
- Legacy terminal `SENT_TERMINAL` evidence remains terminal so hardening cannot accidentally reopen an already-sent intent.
- Unsigned/plain Muse dictionaries degrade to `WAIT_MUSE`; they never become ready.

## Core invariants

- A live lease held by another claimant returns `YIELD_EXISTING` without rewriting its owner.
- Muse binds exact fingerprint + claimant + session + **lease generation**.
- Lease expiry is capped by authenticated Muse expiry.
- A send attempt binds exact body SHA-256 and provider; identical replay is idempotent, changed body/provider is blocked.
- `UNKNOWN` provider result never permits a fresh attempt; reconcile the exact attempt first.
- Provider-confirmed `SENT` is terminal, including a late receipt after lease expiry.
- `external_send`, `muse_arbitration`, `provider_mutation`, `payment`, and `revenue` authority are always false.

## Live workflow

1. Canonicalize the counterparty/route/thread/purpose and acquire a lease without Muse evidence (`WAIT_MUSE`).
2. Ask Muse externally using the normal TokenJunkieLabs coordination path. This module never messages Muse.
3. A controlled adapter retains Muse evidence, constructs the trusted registry, and signs it with the runtime-held key.
4. Re-run `acquire(..., muse=<signed registry>)`. Only one exact, current authenticated selection reaches `READY_SINGLE_WRITER`.
5. Hash final message bytes and call `begin_send(...)` before the separately authorized provider mutation.
6. Bind `SENT` or `UNKNOWN` provider evidence with `observe_send(...)`; never retry a changed body while the result is unresolved.

## Verification

```bash
python -m py_compile revenue/outbound_collision_guard/core.py tests/test_outbound_collision_guard.py tests/test_outbound_collision_guard_release_boundary.py
python -m unittest -v tests.test_outbound_collision_guard tests.test_outbound_collision_guard_release_boundary
python -O -m unittest -v tests.test_outbound_collision_guard tests.test_outbound_collision_guard_release_boundary
python -m revenue.outbound_collision_guard.demo
```

The suite includes signed-registry and legacy-regression hostiles plus the original send/replay boundary behavior.
