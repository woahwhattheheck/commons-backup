# Commercial opportunity custody

`commercial_opportunity_custody` is an internal coordination authority boundary for one commercial pursuit. It exists because a send mutex is not enough: several workers can still independently believe they own the same source/proposal/outreach lane before anyone reaches the provider-send boundary.

## Contract

A pursuit has one stable identity:

- coordination repository (`owner/repo`),
- canonical buyer organization domain,
- canonical source/issuer authority domain,
- stable external opportunity ID.

The Git ref path contains only the SHA-256 of that identity. Source-document revisions are **not** part of the seam key, so an addendum cannot mint a second pursuit. The current source generation is instead state inside the custody chain and may be advanced only by the live WHOLE owner.

Every custody mutation appends one immutable annotated tag through a deterministic generation ref:

```
refs/tags/commercial-opportunity-custody-v1/<seam_sha256>/g/0000000001
refs/tags/commercial-opportunity-custody-v1/<seam_sha256>/g/0000000002
...
```

All mutations race for the same next generation. Git ref creation is create-once: if two workers plan generation `N+1`, at most one deterministic ref can be created. The loser reconciles that ref and receives `HOLD` rather than trying another generation as a silent retry.

The live authority reader lists every generation ref, requires a contiguous chain, reads each annotated tag, checks canonical event bytes/tagger/commit target/predecessor SHA, and replays the state machine. A local mutation receipt explicitly says `APPENDED_NOT_CURRENT_AUTHORITY`; it never proves current ownership because a later transfer/release may already exist.

## Ownership model

There is exactly one WHOLE owner (`actor id + operation id`) or none. The WHOLE owner may create bounded delegates for:

- `source`
- `proposal`
- `outreach`
- `scheduling`
- `fulfillment`
- `settlement`

A delegate receives only that lane. Delegates cannot transfer themselves, expand to another lane, change the source generation, release the pursuit, or transfer WHOLE custody. WHOLE transfer/release clears every delegate rather than accidentally inheriting stale authority.

The operation ID is part of live authority, not just the seat ID. This closes an ABA case where a seat regains the pursuit under a new operation and an old receipt/operation tries to mutate it.

## Required use

Before source/proposal/outreach work, call `authorize_internal_work(...)` against **live Git state** for the exact actor + operation + lane. Do not treat a Slack TAKE, local JSON receipt, or old mutation receipt as a replacement for live verification after a pursuit has adopted this primitive.

This does **not** replace `revenue/outbound_connector_lease` or `tools/outbound_send_guard`. Opportunity custody says who owns internal pursuit work. The outbound lease remains a separate prerequisite immediately before an external send. Holding either one never implies buyer acceptance, submission authority, contract authority, payment, cash, or recognized revenue.

## Existing / pre-adoption pursuits

`compile_legacy_import(...)` intentionally emits a **non-authorizing** receipt. It records prior Slack/source evidence but cannot seize a pursuit. A trusted host/operator must first reconcile the historical owner and seed canonical custody for that owner; until then the legacy receipt remains `LEGACY_CUSTODY_REQUIRES_CANONICAL_OWNER_SEED`.

The library cannot discover old Slack history by itself and does not claim otherwise.

## Example identity

```json
{
  "schema": "commercial-opportunity-custody/v1",
  "repo": "woahwhattheheck/commons",
  "buyer_scope": "utilitysafety.ca",
  "authority_scope": "utilitysafety.ca",
  "opportunity_id": "data-ai-rfp-2026"
}
```

No person name, email address, message body, proposal body, payment data, credential, or raw customer record belongs in this identity or in a custody ref.

## Tests

```bash
python -m unittest -v revenue.commercial_opportunity_custody.test_custody
python -O -m unittest -v revenue.commercial_opportunity_custody.test_custody
python -m py_compile revenue/commercial_opportunity_custody/custody.py revenue/commercial_opportunity_custody/test_custody.py
```

The focused hostile suite covers the live Utility Safety failure class (two independently prepared generation-1 WHOLE claims), delegated-lane boundaries, stale operation/ABA, transfer/release invalidation, source-generation changes without seam split, fabricated/stale receipts, ref replacement, generation gaps, tag tampering, identity transplant, and the external-authority ceiling.
