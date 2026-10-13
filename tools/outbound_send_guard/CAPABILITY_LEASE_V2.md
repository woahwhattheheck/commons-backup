# Proof-of-possession outbound lease v2

`capability_lease` is the current-worker possession layer for the one-touch outbound-send mutex.

It exists because v1 can prove that a public claim is consistent with the live GitHub ref/tag, but all v1 claimant/generation fields are themselves public in the authentic receipt/tag. A different worker can therefore copy winner A's authentic public evidence and supply A's exact values to the v1 verifier. **V1 is useful provider-backed claim consistency, not proof that the current invoker owns the winning generation.**

New send boundaries that need worker ownership must use v2 possession verification. V1 receipts remain valid historical evidence and must not be silently reinterpreted as v2.

## Authority ceiling

A v2 lease proves only two things together:

1. the deterministic buyer+offer ref in the coordination repository points to the exact annotated tag bound to the public claim; and
2. the current caller possesses the 256-bit capability whose SHA-256 commitment is sealed into that tag and receipt.

It does **not** authorize an external send. Every v2 public receipt still has:

```json
{"external_send_authorized":false}
```

Owner approval, content, route, cooldown, DNR, provider state, and every other outbound gate remain separate requirements.

## Why the capability is different from v1 caller fields

Acquisition generates the capability with `secrets.token_hex(32)` inside the v2 acquisition boundary. The public claim cannot select it. The raw capability is passed once to a retention sink **before any provider call**.

Only `SHA256(capability)` is allowed into:

- annotated-tag metadata;
- tag naming material;
- the public lease receipt.

The raw capability is not returned in the public receipt and must not be logged, posted to Slack/GitHub, included in claim JSON, placed on argv, or written into provider metadata.

Because the public receipt/tag expose only a 256-bit commitment, copying all of winner A's public fields does not let worker B satisfy `verify_possession()` without A's privately retained capability.

## Namespace

V2 is deliberately disjoint from the permanent v1 namespace:

```text
schema: outbound-send-lease/v2
receipt: outbound-send-lease-receipt/v2
ref: refs/tags/outbound-lease-v2/<sha256({schema,buyer_scope,offer_scope})>
```

This prevents an old v1 permanent ref from being mistaken for v2 possession authority.

## Public claim

The public claim contains no capability:

```json
{
  "repo":"woahwhattheheck/commons",
  "buyer_scope":"example.com",
  "offer_scope":"lims-migration-validation-pilot",
  "claimant":"Z-Example-Worker",
  "claim_id":"example-lims-20260913",
  "claim_started_at":"2026-09-14T01:56:07Z",
  "anchor_sha":"0123456789012345678901234567890123456789",
  "preflight_sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

`preflight_sha256` is exactly 64 lowercase hex. Invalid claim structure fails before capability retention or provider I/O.

## Library acquisition

`acquire()` requires a capability-retention callback. The generated raw capability is delivered to that callback before any GitHub call; if retention fails, acquisition aborts without provider I/O.

```python
from tools.outbound_send_guard.capability_lease import acquire

private = []
receipt = acquire(
    claim,
    transport,
    retain_capability=private.append,
)
capability = private.pop()
```

The in-memory example is suitable for a process-local trusted boundary only. Shared production pipelines should use a private host store or the CLI's create-exclusive owner-only file path.

## CLI acquisition

The CLI never accepts the capability on argv and never prints it to stdout:

```bash
python -m tools.outbound_send_guard.capability_lease \
  claim.json \
  --capability-out ./private/lease.cap
```

The capability output uses create-exclusive file creation and mode `0600`. On POSIX, the CLI fsyncs both the capability file and its parent directory before any provider mutation, so the new filename is crash-durable before the permanent lease ref can be created. An existing destination is a HOLD; it is never overwritten. Any retention or directory-sync failure aborts before provider I/O.

The printed JSON is the **public** receipt only.

## Possession verification

The current holder supplies its private capability separately:

```python
from tools.outbound_send_guard.capability_lease import verify_possession

lease_possession_is_live = verify_possession(
    receipt,
    claim_capability=capability,
    transport=transport,
)
```

Verification is fail-closed:

1. validate the public receipt and its deterministic digest;
2. validate the raw capability format and require its SHA-256 commitment to equal the receipt commitment **before provider I/O**;
3. recompute the v2 seam/ref from the public receipt;
4. read live provider state even when the original public receipt was `HOLD`, so an outcome-unknown acquisition can be recovered later using the same privately retained capability instead of blindly minting a new capability;
5. read the exact live Git ref and require its object to equal the receipt tag SHA;
6. read the annotated tag and strictly parse its metadata;
7. require exact claim, capability commitment, tag name, target commit, and tagger binding;
8. fail closed on missing, unreadable, malformed, moved, duplicated-key, or uncertain provider evidence.

A `HOLD` receipt does not become authority merely because it exists. Recovery succeeds only when the same retained capability matches the receipt commitment **and** later live ref/tag readback proves that exact receipt tag actually owns the v2 seam. If live state points elsewhere, possession remains false. Do not retry acquisition with a new capability after an outcome-unknown response until this recovery check has been attempted.

A copied authentic receipt plus every exact public winner value but the wrong/missing capability fails before any provider read.

## V1 migration rule

`atomic_lease` + `lease_authority.verify_authoritative_receipt()` v1 remain historical/provider-consistency tools. Their expected claimant/generation arguments are public values, not caller-unmintable possession evidence. They must not by themselves satisfy a current-worker ownership gate.

Do not migrate a permanent v1 ref in place. Acquire under the distinct v2 namespace if the send boundary requires current-worker proof of possession.

## Regression gate

```bash
python -m py_compile \
  tools/outbound_send_guard/capability_lease.py \
  tools/outbound_send_guard/test_capability_lease.py
python -m unittest -v tools.outbound_send_guard.test_capability_lease
python -O -m unittest -v tools.outbound_send_guard.test_capability_lease
```

The focused hostile suite covers exact holder success, copied-winner replay with all public A values, wrong/malformed capability before provider I/O, capability-retention failure before provider I/O, raw-capability non-disclosure, v1/v2 namespace separation, tag/receipt commitment drift, duplicate-key tag metadata, provider uncertainty/ref drift, target/tagger drift, other-owner HOLD rejection, later recovery of an outcome-unknown HOLD using the same retained capability plus exact live ref/tag evidence, create-exclusive `0600` capability custody, parent-directory fsync failure before provider mutation, and malformed public claims before retention/provider mutation.
