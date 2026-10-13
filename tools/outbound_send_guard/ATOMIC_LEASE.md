# Atomic outbound send lease v1 — provider-backed claim consistency

`atomic_lease` closes the first half of a concurrency gap: two workers can both observe "not sent yet" and both cross an outbound provider boundary. It creates one permanent deterministic Git ref for a buyer+offer seam so only one public claim generation can own that v1 ref.

**Current status:** v1 is retained for historical/provider-backed claim-consistency evidence. It does **not** prove that the current invoker possesses the winning generation, because claimant/id/time/anchor/preflight are public in the authentic receipt/tag and can be copied together. New send boundaries that need current-worker ownership must use [`CAPABILITY_LEASE_V2.md`](./CAPABILITY_LEASE_V2.md) and `capability_lease.verify_possession()`.

A lease never authorizes an external send. All receipts keep `external_send_authorized=false`; owner/content/DNR/cooldown/route/provider gates remain separate.

## V1 acquisition model

The caller supplies:

- `repo` — coordination repository;
- `buyer_scope` — stable organization/recipient seam;
- `offer_scope` — exact commercial offer/problem seam;
- `claimant`, `claim_id`, `claim_started_at` — public claim identity/generation;
- `anchor_sha` — existing coordination-repo commit object;
- `preflight_sha256` — **exactly 64 lowercase hex**, binding separate preflight evidence.

Malformed/non-SHA-256 `preflight_sha256` is rejected before any provider call. This preserves the later repair that prevents an invalid 40-hex/uppercase claim from creating the permanent seam ref and poisoning that seam.

The v1 seam is:

```text
refs/tags/outbound-lease-v1/<sha256({schema,buyer_scope,offer_scope})>
```

Acquisition first creates a non-authoritative annotated tag object containing public claim metadata, then atomically creates the deterministic ref. `201` with exact object proves that public claim won. `422` or an indeterminate ref-create response gets exactly one live readback. Missing, unreadable, malformed, or other-owned readback returns HOLD.

The permanent buyer+offer ref is intentional one-touch v1 state. Route changes must not mint a fresh buyer seam.

## V1 verification boundary

`atomic_lease.verify_receipt()` is integrity-only: schema, internal consistency, and caller-recomputable receipt digest.

`lease_authority.verify_authoritative_receipt()` adds live provider readback and checks that the v1 ref/tag is consistent with the supplied expected public claim values. It validates repo, seam, claimant/id/start, anchor, preflight, target, deterministic tag name, tagger, and the live ref -> tag relation.

That is useful evidence, but **the word "expected" is not an authentication root**. A different worker can copy winner A's authentic receipt, read A's exact public values from the receipt/tag, and call the v1 verifier with those same A values. V1 therefore proves:

> live provider state is consistent with this supplied public claim

It does **not** prove:

> the current process/worker privately possesses the winning claim generation

Do not use v1 alone as the final mutual-exclusion prerequisite at a send boundary. Use v2 proof of possession for that purpose.

## Example v1 claim

```json
{
  "repo":"woahwhattheheck/commons",
  "buyer_scope":"example.com",
  "offer_scope":"lims-migration-validation-pilot",
  "claimant":"Z-Meridian-913506-L91",
  "claim_id":"example-lims-zmer-20260913",
  "claim_started_at":"2026-09-13T09:26:20Z",
  "anchor_sha":"0123456789012345678901234567890123456789",
  "preflight_sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

Historical v1 acquisition:

```bash
python -m tools.outbound_send_guard.atomic_lease claim.json
```

The token is environment-only; redirects are refused; network uncertainty fails closed/readback-only.

## Regression gates

V1 acquisition/consistency:

```bash
python -m py_compile \
  tools/outbound_send_guard/atomic_lease.py \
  tools/outbound_send_guard/lease_authority.py \
  tools/outbound_send_guard/test_atomic_lease.py \
  tools/outbound_send_guard/test_lease_authority.py
python -m unittest -v \
  tools.outbound_send_guard.test_atomic_lease \
  tools.outbound_send_guard.test_lease_authority
python -O -m unittest -v \
  tools.outbound_send_guard.test_atomic_lease \
  tools.outbound_send_guard.test_lease_authority
```

Current-worker possession v2:

```bash
python -m py_compile \
  tools/outbound_send_guard/capability_lease.py \
  tools/outbound_send_guard/test_capability_lease.py
python -m unittest -v tools.outbound_send_guard.test_capability_lease
python -O -m unittest -v tools.outbound_send_guard.test_capability_lease
```

V1 hostiles still cover provider/ref/tag drift and malformed-preflight seam poisoning. V2 adds a private capability commitment and the decisive replay hostile: B-context + A's unchanged authentic public receipt/values must fail without A's raw capability, before provider I/O.
