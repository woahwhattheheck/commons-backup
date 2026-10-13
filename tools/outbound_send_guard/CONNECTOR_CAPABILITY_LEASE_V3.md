# Connector-native proof-of-possession outbound lease v3

`connector_capability_lease` is an additive current-worker possession protocol for environments whose GitHub connector can create blobs, trees, commits, and branches but cannot create annotated tag objects.

It does **not** reinterpret or weaken `outbound-send-lease/v2`. V2 remains valid and authoritative wherever its annotated-tag transport is available. V3 uses a distinct schema and ref namespace so historical v1/v2 evidence cannot be mistaken for v3.

## What v3 proves

A held v3 receipt plus successful live `verify_possession()` proves that:

1. the deterministic buyer + offer lease branch points to the exact capability-bound off-main lease commit;
2. that commit has the exact frozen anchor commit as its parent;
3. its deterministic metadata file contains the exact frozen claim and only the SHA-256 commitment of a 256-bit capability; and
4. the current caller possesses the raw capability matching that commitment.

It does **not** authorize a send. Every plan, intent, metadata record, and receipt binds `external_send_authorized=false`. Owner approval, content, route, DNR/cooldown, provider state, buyer relationship state, and every other outbound gate remain independent requirements.

## Why this closes the connector transport gap

Some connector catalogs expose create-blob, create-tree, create-commit, create-branch/ref, and read-ref/commit/file operations but not `POST /git/tags`. V3 composes only those exposed primitives. The authority event is create-exclusive deterministic branch creation:

```text
refs/heads/outbound-lease-v3/<sha256({schema,buyer_scope,offer_scope})>
```

Both contenders may create non-authoritative blobs/trees/commits. Only one deterministic branch can exist. A copied public winner plan/intent/receipt is still insufficient because the raw 256-bit capability is never public.

## Acquisition recipe

1. Freeze the exact public claim: repo, buyer scope, offer scope, claimant, claim ID, start time, anchor commit, and preflight SHA-256.
2. Call `prepare_acquisition(claim, retain_capability=...)`. The callback receives the raw capability once. Retain it privately before any acquisition mutation. Never print it, post it, place it in GitHub metadata, or pass it on argv.
3. Create the plan's `metadata_json` as a blob.
4. Read the frozen anchor commit's tree, create a tree based on it with exactly the plan's `metadata_path` added/replaced by that blob, then create one commit with the exact anchor as parent. The lease commit stays off main.
5. Call `bind_lease_commit(plan, lease_commit_sha)` and atomically create `intent["branch_name"]` pointing to that exact commit. Do not force-update an existing v3 lease branch.
6. Re-read the deterministic branch, the exact head commit parent, and the metadata file at that branch.
7. Compile `receipt_from_readback(...)`. Only `decision=LEASE_HELD` may proceed to possession verification.
8. Call `verify_possession(receipt, claim_capability=private_capability, live_branch_sha=..., live_parent_sha=..., live_metadata_json=...)` from fresh provider evidence immediately before the external send.
9. Preserve every independent route/content/DNR/provider gate. One external provider mutation maximum for the claimed generation.

If branch creation returns an already-exists/conflict response, do not overwrite it. Read the existing deterministic branch and compile a HOLD receipt unless it is the exact bound lease commit. Even if an observer races to create the ref pointing to the winner's already-public commit, only the secret holder can pass possession verification; observers can at most cause a fail-closed denial of service.

## Public / private boundary

Public: plan, capability commitment (`SHA256(raw_capability)`), metadata blob, off-main lease commit, deterministic lease branch/ref, intent, and receipt.

Private: the raw 64-hex-character capability only.

Do not put the raw capability in GitHub, Slack, logs, provider metadata, issue/PR text, process argv, or a public artifact. Production pipelines should retain it in a private owner-only store. A process-local in-memory sink is acceptable only for a single trusted execution boundary.

## Verification failures

Possession fails closed on any wrong/missing/malformed private capability; deterministic branch missing or moved; branch head differing from the bound lease commit; lease commit parent differing from the frozen anchor; metadata missing/unreadable/non-canonical/tampered; claim/capability commitment drift; receipt digest drift; wrong schema or v1/v2 namespace reuse; or malformed provider object IDs.

No failure path authorizes fallback to v1 for a boundary that requires current-worker possession.

## Focused regression gate

```bash
python -m py_compile \
  tools/outbound_send_guard/connector_capability_lease.py \
  tools/outbound_send_guard/test_connector_capability_lease.py
python -m unittest -v tools.outbound_send_guard.test_connector_capability_lease
python -O -m unittest -v tools.outbound_send_guard.test_connector_capability_lease
```

The hostile suite covers exact-holder success, copied-public-evidence replay with the wrong secret, retention failure, raw-secret non-disclosure, deterministic seam/v1-v2 namespace separation, other-owner head, anchor drift, metadata tamper, plan/intent/receipt tamper, unknown fields, malformed secret, missing provider evidence, and duplicate-key/non-canonical metadata substitution.
