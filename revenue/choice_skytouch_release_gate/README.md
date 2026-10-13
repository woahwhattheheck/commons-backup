# Choice / SkyTouch property release evidence — synthetic delivery core

This package is a provider-free executable acceptance core behind the bounded Choice Hotels / SkyTouch outreach lane `CHOICE-SKYTOUCH-RELEASE-GATE-ZP913443-20260913`. It works only on caller-supplied synthetic property configuration snapshots. It does not log in to SkyTouch, change a property, call an integration, or authorize an external effect.

## Contract

A release bundle contains one exact baseline snapshot, one candidate snapshot, an explicit declared change set, and exact post-change invariants. The gate:

- SHA-256 binds the canonical baseline and rejects a stale baseline digest;
- binds one property identity and requires revision advancement;
- compares the complete flat configuration surface so undeclared mutations cannot hide behind a valid declared subset;
- requires every declared before/after value to match the baseline/candidate evidence;
- evaluates named exact-value invariants and HOLDs on any failure;
- emits deterministic logical-effect intents only on PASS, with stable IDs and fingerprints;
- maintains a provider-free replay ledger: a second presentation of the same logical effects emits zero new intents, while the same logical ID with different bytes fails closed;
- emits a self-digested receipt whose `external_effect_authorized`, `buyer_acceptance_claimed`, and `revenue_claimed` fields are always false.

The parser rejects duplicate JSON keys, non-finite numbers, unknown schema fields, nested config payloads, malformed identifiers/paths, duplicate declared paths, duplicate invariant names, and oversized inputs.

## Acceptance fixture

`acceptance.py` generates 20 independent synthetic properties. Each candidate release declares two changes and two invariants. The fixture proves:

- 20/20 release evidence PASS;
- 40/40 first-pass logical effects appear once;
- replay of every release against the accumulated effect ledger emits **zero** new effects and collapses all 40 exact duplicates;
- change/invariant ordering does not change receipt identity;
- stale base, undeclared mutation, failed invariant, property-ID drift, and non-advancing revision each HOLD independently.

Run from the Commons root:

```bash
python -m unittest -v revenue.choice_skytouch_release_gate.test_gate
python -O -m unittest -v revenue.choice_skytouch_release_gate.test_gate
python -m revenue.choice_skytouch_release_gate.acceptance
python -m py_compile \
  revenue/choice_skytouch_release_gate/gate.py \
  revenue/choice_skytouch_release_gate/acceptance.py \
  revenue/choice_skytouch_release_gate/test_gate.py
```

## Integration boundary

The core intentionally stops before provider access. A future buyer-funded adapter may map approved SkyTouch/property configuration evidence into this schema and may separately execute buyer-authorized provider operations. This package itself has no network client, credential surface, deployment behavior, property write, payment path, contract state, or customer communication. `PASS` means only that the supplied synthetic release-evidence bundle satisfies the deterministic acceptance contract.
