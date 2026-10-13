# Hyperagent agent-event → Slack transcript pilot proof

This package is the internal fulfillment-readiness artifact for the already-offered Hyperagent paid pilot. It is deliberately **provider-neutral and zero-network**: it does not call Hyperagent, Slack, Gmail, or any buyer system, and it carries no private Hyperagent data.

## What is proved

The package normalizes three intentionally heterogeneous synthetic backend event schemas (`stream`, `trace`, `envelope`) into deterministic logical transcript artifacts. Source identity is scoped to **backend + source run + source event**, so backend-local event IDs may safely repeat across distinct runs. The checked-in fixture contains **30 text events** spanning exactly **6 logical transcript artifacts**. A clean replay is idempotent: the second full replay emits **0 new logical messages**, while a reused source identity with changed semantics fails closed as a conflict.

Mutating-action events are approval gated. An action is emitted only when one approval is current, binds the exact normalized run/action/generation **and the canonical `event_semantics_sha256` of that mutating event**, and authenticates under **retained runtime approval authority supplied outside this repository**. One authenticated approval cannot authorize a distinct first-seen event identity or a different text/thread/sequence under the same action tuple. Approval data cannot self-authorize: `authority_tag` is HMAC-SHA256 over the canonical approval fields, verified with a runtime key that is never committed here. Missing authority key, missing approval, denied approval, stale approval, foreign run/generation, ambiguous approval evidence, or malformed/unauthenticated approval evidence cannot yield an approved action artifact.

Approval freshness uses captured **process UTC**. The public `TranscriptProjector.ingest()` API accepts no caller-provided `as_of` timestamp, so an expired approval cannot be replayed merely by asking the projector to evaluate itself in the past. The only deterministic caller-clock surface is `project_fixture()`, and it rejects both approvals and `MUTATING_ACTION`; it therefore cannot mint or backdate authority.

Every admitted mutating message carries both its immutable `approval_id` and `approval_receipt_sha256`, binding the artifact to the exact authenticated approval generation. Even then, `external_send_authorized` remains `false`; this package never grants real Slack/provider send authority.

Strict-input handling rejects duplicate JSON keys, non-finite numbers, bool-as-int controls, noncanonical UTC, malformed opaque IDs, and non-scalar Unicode before canonical UTF-8 hashing. CLI contract/resource errors return status 2 without a traceback or output artifact.

JSON input permits at most **128 nested objects or arrays** (`MAX_JSON_NESTING_DEPTH`). The root object or array counts as depth 1; a root scalar has depth 0. Brackets and braces inside quoted strings do not count. An iterative scan checks this bound before decoding, including escaped quotes and backslashes, so excess-depth input raises `ValidationError` independently of the Python decoder's recursion behavior. The CLI returns status 2 and creates no output artifact for this error.

## Approval contract

The authenticated approval object is:

```json
{
  "approval_id": "ap-123",
  "run_id": "run_...",
  "action_id": "send",
  "generation": 2,
  "event_semantics_sha256": "<64 lowercase hex of canonical event.semantics()>",
  "decision": "APPROVE",
  "issued_at": "2026-09-16T18:00:00Z",
  "expires_at": "2026-09-16T19:00:00Z",
  "evidence_sha256": "<64 lowercase hex>",
  "authority_tag": "<64 lowercase hex>"
}
```

The issuer computes:

```text
authority_tag = HMAC-SHA256(
  approval_auth_key,
  canonical_json(all fields above except authority_tag)
)
```

`approval_auth_key` must be 32–128 bytes and is injected by the trusted runtime when constructing `TranscriptProjector`. No key, token, buyer credential, or production approval secret is checked into Commons.

The HMAC is an internal pilot boundary, not a claim that a future buyer must use shared-key approvals. A paid integration may replace the verifier with the buyer's approved signature/service mechanism while preserving the exact-generation, freshness, and receipt properties.

## Run the acceptance proof

```bash
python -m unittest -v \
  revenue.hyperagent_slack_transcript.test_adapter \
  revenue.hyperagent_slack_transcript.test_stateful \
  revenue.hyperagent_slack_transcript.test_public_surface
python -O -m unittest -v \
  revenue.hyperagent_slack_transcript.test_adapter \
  revenue.hyperagent_slack_transcript.test_stateful \
  revenue.hyperagent_slack_transcript.test_public_surface
python test_hyperagent_slack_transcript.py
python -m revenue.hyperagent_slack_transcript.cli \
  revenue/hyperagent_slack_transcript/fixture.json \
  /tmp/hyperagent-transcripts.json
```

Expected text-fixture invariant: `artifact_count == 6`, `message_count == 30`. The root `test_hyperagent_slack_transcript.py` bridge is discovered by the retained Commons CI battery and executes the focused suite in both normal and optimized (`-O`) modes; no dedicated active workflow is required.

The mutation tests use dedicated **test-only** key material and broad synthetic validity windows. They prove that a correctly authenticated exact-generation approval can yield one offline candidate, while missing key, wrong key, post-signature tampering, stale windows, wrong run/generation, denial, duplicate identity mutation, caller-clock injection, and a reused approval against a distinct event semantic all fail closed.

## Commercial handoff

This is a product proof for a bounded paid pilot, not a free production deployment. A paid engagement can replace the three synthetic adapters with buyer-approved backend mappings while preserving the same acceptance contract:

1. backend + run + source-event identity and semantic conflict detection;
2. deterministic run/thread/message projection;
3. replay without duplicate logical messages;
4. authenticated exact action-generation *and event-semantics* approval binding before mutating-action projection;
5. process/trusted-time freshness rather than caller-authored clock authority;
6. deterministic artifacts and exact approval receipts suitable for buyer review.

Buyer/runtime owners retain credentials, production routing, deployment, data policy, Slack workspace administration, approval-issuer key custody, and human approval authority. The code makes no claim of buyer acceptance, contract, award, payment, settlement, or recognized revenue.

## Truth boundary

- Synthetic fixture only; no buyer/private event payloads.
- Offline artifacts only; no network calls.
- `external_send_authorized` is always false.
- No email, DM, support reply, Slack send, provider mutation, deployment, payment, or revenue recognition.
- No buyer approval secret is committed; the package only defines and verifies a bounded internal pilot authority contract.

## Lineage

The canonical product, normalization core, fixture, replay model, CLI, and original tests landed through **#15057**. The post-merge authority fix preserves that normalization implementation byte-for-byte in private `_legacy_adapter.py`; public imports route through the hardened authority layer. Original #15057 product/source/finalizer credit remains intact; the fix-forward changes only the approval/time trust boundary and predecessor-killing tests/documentation.
