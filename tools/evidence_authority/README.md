# Source-bound evidence authority kernel

Isolated primitive under `tools/evidence_authority/**`. Candidate claims
never self-type `PROVIDER_AUTHENTICATED` / `BUYER_AUTHENTICATED`. A
positive result requires:

1. **Out-of-band retained root.** The expected authority-manifest SHA-256
   is a verifier input, never read from the candidate.
2. **Closed source inventory.** Manifest paths are the complete set.
   Missing, extra, duplicate, reordered, aliased, or reminted sources
   fail closed.
3. **Exact bytes → digest.** Every source digest is recomputed from
   retained bytes. A 64-hex string is not authenticity.
4. **Derived authority.** Status comes from a retained record, not a
   caller boolean or label.
5. **Identity binding.** Issuer, subject, kind, scope, generation, and
   canonical payload must match. Cross-account / buyer / product /
   opportunity / generation transplants fail closed.
6. **Currentness ≠ integrity.** `compile` / `verify-current` use
   verifier-owned process UTC. `verify` is historical integrity only and
   cannot remint current-positive authority from a backdated clock.
7. **Strict JSON.** Duplicate keys, NaN/Infinity, huge ints, bool/int
   aliases, lone surrogates, unknown fields, and oversized sets fail
   closed in normal Python and real `python -O`.
8. **Deterministic receipt.** Binds candidate, pinned root, manifest,
   source-set, derived facts, currentness, implementation contract, and
   all-false external authority.

A verified receipt proves only that retained source bytes support a
bounded claim at a bounded generation/currentness class. It is not
buyer contact, a provider session, spend, payment, or revenue.

## CLI

```
python -m tools.evidence_authority.cli compile candidate.json manifest.json <pinned-root> \
  --source records/alpha.json=fixtures/alpha.json
python -m tools.evidence_authority.cli verify candidate.json manifest.json <pinned-root> receipt.json \
  --source records/alpha.json=fixtures/alpha.json
python -m tools.evidence_authority.cli verify-current candidate.json manifest.json <pinned-root> \
  --source records/alpha.json=fixtures/alpha.json
```

Domain errors print `ERROR: …` on stderr and exit 2, with no traceback.

## Tests

```
python -m unittest -v test_evidence_authority
python -O -m unittest -v test_evidence_authority
python -m py_compile tools/evidence_authority/*.py test_evidence_authority.py
```

## Adapter

See `adapter_provider_cost_truth.md`. Do not edit the live
`tools/provider_cost_truth` carrier until its owner consumes this
primitive.
