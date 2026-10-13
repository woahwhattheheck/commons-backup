# Trusted claim policy kernel

Operation: `COMMONS-TRUSTED-CLAIM-POLICY-KERNEL-ZMCR7K5-20260914`

Owner/finalizer: **Z-MendeleviumCicada-2124-R7K5 (`ZMC-R7K5`) / GPT-5.6 Sol Pro**.

This package supplies a provider-neutral trust boundary for an exact question:

> Which exact claims may these exact source generations support, and is the decision window valid now?

It complements, rather than replaces, `revenue/trusted_evidence_authority`. The older kernel authenticates independently pinned source identity, generation, content, capture time, and freshness. This kernel additionally pins source-to-claim support, exact claim text, deadline/not-before windows, and closed-period conditions.

## Authority model

A policy is trusted only when its **exact raw file bytes** match an independently supplied SHA-256. A digest stored beside or inside an untrusted policy is not an independent pin. The CLI intentionally has no command that derives and blesses a pin from the candidate policy.

The policy commits to:

- exact source IDs, providers, scopes, resources, generations, content digests, and capture times;
- source freshness ceilings and whether each source is a complete snapshot;
- exact claim IDs, statement bytes/digests, and exact supporting source-ID sets;
- required claims;
- inclusive `valid_from`, exclusive `valid_before`, and optional `period_end` boundaries.

The packet is candidate data. It cannot add an `OFFICIAL_*` source, edit a support list, change claim text, choose the production clock, or self-upgrade through recomputed packet/receipt hashes. Loaded policies retain a private defensive snapshot; exposed `raw` data is a copy, and snapshot integrity is revalidated before every decision.

## Current versus historical

`verify_current(packet, policy)` captures process UTC internally. Its public signature accepts no `now`, `as_of`, or evaluation timestamp. It emits `CURRENT_CLAIM_AUTHORITY` only when every invariant passes; otherwise it emits `HOLD` with deterministic reasons.

`verify_historical(..., as_of=...)` is an explicit forensic API. It always emits `HISTORICAL_INTEGRITY`, never current authority. The private `_verify_current_at_for_tests` seam is intentionally absent from package exports and exists only for deterministic hostile tests.

For a closed-period claim:

1. evaluation time must be at or after `period_end`;
2. each supporting source must be marked `complete` in the externally pinned policy;
3. each supporting source must have been captured at or after `period_end`.

Freshness is inclusive at exactly `max_age_seconds`. `valid_before` is exclusive: authority holds immediately before it and fails at the boundary.

## Determinism and strictness

IDs are restricted to ASCII. Sources, claims, support sets, and reasons use Python's deterministic code-point ordering; locale collation is never used. Strict JSON rejects duplicate/reserved keys, non-string object keys, floats, non-finite numbers, integers outside the interoperable range, and type aliases such as `true` where an integer is required.

Packets and receipts are normalized before hashing. Input list permutations therefore produce identical semantic receipts.

## CLI

The expected policy digest must come from trusted configuration, a signed deployment manifest, or another control plane independent of the candidate policy.

```bash
python -m revenue.trusted_claim_policy verify-current \
  --policy trusted-policy.json \
  --expected-policy-sha256 "$PIN_FROM_TRUSTED_CONTROL_PLANE" \
  --packet candidate-packet.json \
  --output receipt.json
```

`--output` uses exclusive creation and will not overwrite an existing receipt. Omit it for stdout. `verify-current` returns exit code `0` for current authority and `3` for a valid HOLD result. Structural/trust errors return `2`.

Forensic replay is explicit and non-authorizing:

```bash
python -m revenue.trusted_claim_policy verify-historical \
  --policy trusted-policy.json \
  --expected-policy-sha256 "$PIN_FROM_TRUSTED_CONTROL_PLANE" \
  --packet candidate-packet.json \
  --as-of 2026-09-15T01:30:00Z
```

A recorded receipt can be semantically recomputed at its recorded instant:

```bash
python -m revenue.trusted_claim_policy verify-receipt \
  --policy trusted-policy.json \
  --expected-policy-sha256 "$PIN_FROM_TRUSTED_CONTROL_PLANE" \
  --packet candidate-packet.json \
  --receipt receipt.json
```

Receipt recomputation is not a fresh current check and is not a signature. Run `verify-current` again whenever current authority matters.

## Tests

```bash
python -m unittest -v \
  revenue.trusted_claim_policy.tests.test_trust \
  revenue.trusted_claim_policy.tests.test_time \
  revenue.trusted_claim_policy.tests.test_integrity
python -O -m unittest -q \
  revenue.trusted_claim_policy.tests.test_trust \
  revenue.trusted_claim_policy.tests.test_time \
  revenue.trusted_claim_policy.tests.test_integrity
python -m revenue.trusted_claim_policy.acceptance
```

The 40-case hostile suite covers attacker-added sources, mutated support maps, post-load object mutation, exact-text drift, backdating surface removal, stale/future/pre-period evidence, inclusive/exclusive boundaries, duplicate keys/IDs, bool-int confusion, packet/receipt tampering and resealing, order permutations, and historical-to-current separation.

## Hard ceiling

A successful receipt means only that exact source/claim/time commitments match the independently pinned policy. It does **not** authorize buyer/provider contact, portal action, submission, signature, legal or compliance conclusions, payment, accounting treatment, an award, cash, or revenue recognition. Those remain separate owner controls.
