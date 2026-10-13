# Muse publication selection gate

`muse_selection_gate.py` is the Commons-side coordination seam for the live operational rule: before outbound publication, workers ask the Muse assistant which exact candidate may proceed. It composes with the existing relationship/DNR/provider gates and connector-native outbound lease. It never replaces those controls and never authorizes a provider mutation by itself.

## Current authority state

**Important current-main rule:** raw/caller-authored `muse-publication-arbitration-snapshot/v1` JSON is not an independently authenticated Slack/provider record. Therefore this module intentionally **cannot mint or verify a current-positive `SELECTED` authority receipt from raw snapshot JSON**.

A syntactically coherent raw snapshot whose decision would otherwise be `SELECTED` is compiled as `HOLD` with:

- `SNAPSHOT_AUTHORITY_UNVERIFIED`
- `CURRENT_SELECTED_REQUIRES_PROVIDER_AUTHENTICATED_SNAPSHOT`

This is deliberate fail-closed behavior. Live operational Muse arbitration may still be performed through the actual Muse conversation; this module does not pretend that caller-authored JSON proves what the provider said. A future provider-authenticated adapter must establish an independent trust root before current-positive machine verification is re-enabled.

Legacy `muse-publication-selection-receipt/v1` receipts are not current authority. Current receipts use `muse-publication-selection-receipt/v2` and are truth-labelled `authority_mode=UNAUTHENTICATED_SNAPSHOT_ANALYSIS`.

## Why the boundary changed

The first landed implementation allowed three unsafe compositions:

1. a direct importer could supply its own `now=` value and backdate freshness checks;
2. a once-minted `SELECTED` receipt had no verifier-owned current expiry boundary; and
3. snapshot conversation/arbiter/event fields and the expected IDs were supplied by the same caller, so a complete-looking Muse transcript could be fabricated locally.

The fix-forward removes caller-selected time from the public current compiler, samples process UTC internally, rejects legacy v1 receipts as current, and keeps raw-snapshot positive selection fail-closed until independent provider authentication exists.

## Candidate identity

The strict candidate schema remains `muse-publication-candidate/v1`.

`publication_key` hashes the collision domain only:

- `buyer_scope_sha256`
- `recipient_fingerprint`
- `offer_scope`
- `route_kind`

It intentionally excludes worker identity and wording so two workers pursuing the same buyer/recipient/offer/route collide.

`candidate_digest` separately binds candidate ID, worker, exact message SHA-256, request time, and the exact public v3 outbound-lease identity. The private lease capability must never enter Slack, GitHub, candidate JSON, snapshot JSON, or receipts.

## Raw Muse snapshot analysis

The raw snapshot schema remains `muse-publication-arbitration-snapshot/v1`. The compiler still validates:

- complete history declaration;
- configured conversation and arbiter IDs;
- canonical Slack timestamps and user IDs;
- request / snapshot / event chronology;
- freshness and future-skew bounds;
- exact candidate request cardinality;
- decision sender identity;
- multiple-winner conflicts;
- request-to-decision latency;
- cancellation / rejection ordering; and
- selection TTL during analysis.

Defaults remain short-lived: 120s snapshot freshness, 30s future skew, 600s decision latency, and 600s selection TTL.

Those checks are useful for denial and diagnostics, but **they are not provider authentication**. A raw snapshot that would be positive is therefore converted to `HOLD` before receipt publication.

## Receipt and verification rules

Current receipts are `muse-publication-selection-receipt/v2` and always state:

```json
{
  "authority_mode": "UNAUTHENTICATED_SNAPSHOT_ANALYSIS",
  "snapshot_authenticated": false,
  "snapshot_authentication_sha256": null,
  "requires_current_worker_lease_possession": true,
  "requires_fresh_provider_preflight": true,
  "side_effects_authorized": false
}
```

`verify_receipt()` is a **current** verifier. It samples process UTC internally; there is no public caller-supplied verification clock. It rejects future-invalid compiled timestamps, legacy v1 receipts, malformed/tampered receipts, and every raw-snapshot `SELECTED` receipt.

`verify_selected_binding()` therefore remains fail-closed (`False`) until a separate provider-authenticated Muse adapter exists.

The v2 structural selection binding includes `valid_until` so a future authenticated adapter cannot omit expiry from the exact candidate binding. The current raw-snapshot compiler never exposes that structural field as current positive authority.

## Operational Muse wire format

Agents may still use the live Muse process. Candidate/decision machine records should retain exact IDs and digests, for example:

```text
MUSE_PUBLICATION_CANDIDATE_V1 {"candidate_digest":"<sha256>","candidate_id":"<opaque-id>","publication_key":"<sha256>","worker_id":"<swarm-id>"}
```

```text
MUSE_PUBLICATION_DECISION_V1 {"candidate_digest":"<sha256>","candidate_id":"<opaque-id>","decision":"SELECTED","publication_key":"<sha256>","worker_id":"<swarm-id>"}
```

These records help collision matching; copying them into JSON does **not** authenticate them. The independent provider adapter is the missing trust boundary.

## CLI

```bash
python -m tools.outbound_send_guard.muse_selection_gate \
  --candidate candidate.json \
  --snapshot muse-snapshot.json \
  --conversation-id D0C1U7TUZEC \
  --arbiter-user-id U0C0TKRTQHZ \
  --out muse-selection-receipt.json
```

Exit codes:

- `3` — `NOT_SELECTED`
- `4` — `HOLD` (including every raw-snapshot would-be `SELECTED`)
- `2` — invalid input or output-publication failure

Exit `0` is reserved for a future independently authenticated positive path and is not reachable from the present raw-snapshot compiler. `--out` is create-exclusive; an existing path is never overwritten.

## Regression gate

```bash
python -m py_compile \
  tools/outbound_send_guard/muse_selection_gate.py \
  tools/outbound_send_guard/test_muse_selection_gate.py
python -m unittest -v tools.outbound_send_guard.test_muse_selection_gate
python -O -m unittest -v tools.outbound_send_guard.test_muse_selection_gate
```

The focused suite covers caller-clock injection, fabricated two-event transcripts, legacy-v1 rejection, fail-closed selected verification, expiry binding, stale/future/incomplete snapshots, wrong conversation, non-arbiter decisions, multiple winners, cancellation, duplicate message IDs/JSON keys, candidate/lease integrity, tamper attempts, and real CLI behavior.

## Provider-mutation ceiling

Even after a future authenticated Muse adapter exists, a selected arbitration receipt will remain insufficient by itself. Immediately before any email/contact-form/direct-message/provider mutation, the sender must independently satisfy live relationship/DNR/content/provider checks, current-worker v3 lease possession, and fresh provider/mailbox preflight, and then perform at most the separately authorized mutation.
