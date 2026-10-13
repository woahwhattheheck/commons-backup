# Provider relationship census / custody gate

`relationship_census.py` closes the historical-owner race that exact-recipient dedupe and a buyer+offer atomic lease cannot see by themselves. It is **offline**: callers export a complete provider/workspace census, authenticate that snapshot with a provider-scoped HMAC, and feed the exact JSON bytes to this tool before any outreach path is considered.

This gate never sends mail, mutates Gmail/Slack/provider state, schedules work, or authorizes an external side effect. A non-HOLD result only projects custody. Downstream callers still require the ordinary outbound send guard and the atomic send lease.

## Identity and PII boundary

The input names the buyer/account with an opaque `target_scope`; raw email addresses are rejected there. Routes are lowercase SHA-256 hashes only. Each route observation carries `target_binding_sha256 = SHA256(canonical({schema_version, target_scope, route_sha256}))`. The signed provider snapshot also binds the target and sorted route set, so a route-history row copied from a different target yields `HOLD` even if somebody re-signs the malformed census.

The receipt contains the opaque target, route hashes, provider/workspace hash, content digests, relationship owner/generation, decision, and reasons. It never contains raw route addresses.

## Provider authority

`authority.signature_sha256` is HMAC-SHA256 over the canonical authority material: authority schema/key id, target scope, sorted route hashes, and normalized `census`. The CLI gets the secret only from `OUTBOUND_RELATIONSHIP_CENSUS_HMAC_KEY_HEX` (at least 32 bytes); the secret is never accepted in the JSON and never appears in receipts.

Invalid/unsigned authority, incomplete coverage, a stale snapshot, a far-future snapshot, target-binding failures, a current-owner/generation mismatch, or transfer defects all project `HOLD` rather than send authority.

Default freshness is 900 seconds with at most 300 seconds of future skew. CLI bounds can make those windows stricter or looser, but never grant send authority.

## Relationship states

Supported states are `CLEAR`, `ACTIVE_OWNER`, `WAITING_REPLY`, `INBOUND_NEEDS_OWNER`, `UNSUBSCRIBED`, `DNR`, `HARD_BOUNCE`, `TRANSFER_PENDING`, `TRANSFERRED`, and `CLOSED`.

- `CLEAR` with a valid complete snapshot projects `CUSTODY_CLEAR`.
- Non-clear ownership can project `CURRENT_OWNER` only when the current worker and claimed generation match the live relationship and route observations.
- `UNSUBSCRIBED`, `DNR`, and `HARD_BOUNCE` remain `HOLD` even for the owner: custody is not consent or deliverability authority.
- `TRANSFER_PENDING` remains `HOLD`.

## Explicit transfer

A `TRANSFERRED` census must include `census.transfer`. The record is target/route-set bound and must prove:

1. `to_generation == from_generation + 1`;
2. release by the prior owner, or an actor explicitly attested with `release_authority=ADMIN`;
3. acceptance by the new owner;
4. release occurs before acceptance and both precede the provider snapshot;
5. the transferred owner/generation exactly equal the live relationship owner/generation.

The normalized transfer record receives its own `transfer_receipt_sha256` in the custody receipt, making the transfer assertion content-addressed and immutable at the receipt layer.

## CLI

```bash
export OUTBOUND_RELATIONSHIP_CENSUS_HMAC_KEY_HEX='<64+ hex chars>'
python -m tools.outbound_send_guard.relationship_census \
  --census provider-census.json \
  --out custody-receipt.json
```

The CLI reads the census bytes once, rejects duplicate JSON keys and non-finite numbers, and create-exclusively publishes the receipt using same-directory staging + atomic hard-link publication. It refuses to overwrite an existing receipt.

Exit codes: `0` for a valid non-HOLD custody projection, `4` for a valid `HOLD` receipt, and `2` for malformed input/configuration or publication failure.

## Composition

A caller that wants to send must independently satisfy all of the following at the same live operation boundary:

1. provider relationship census/custody projection here;
2. existing mailbox + Slack outbound dedupe authority (#13625 family);
3. existing buyer/route scope aggregation when multiple verified routes are relevant;
4. existing atomic buyer+offer lease / capability possession (#13689 family);
5. any route-lifecycle, unsubscribe, complaint, or bounce policy.

No result from this module substitutes for any of those gates.
