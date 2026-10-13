# Commercial reply guard

`tools/commercial_reply_guard` is the post-routing companion to
`tools/inbound_reply_router`.

The inbound router answers **who owns a real inbound event and what custody queue
it belongs in**. It intentionally does not authorize a reply. This guard takes
that content-addressed router receipt, one bounded owner policy, and one exact
reply proposal and answers a narrower question:

> may the exact body digest be prepared as a factual draft, or must the event be
> held, suppressed, repaired, or escalated to the owner?

It never sends email, opens a new thread, moves money, accepts a contract,
recognizes revenue, or infers buyer acceptance.

## Decisions

- `DRAFT_ALLOWED` — the exact `body_sha256` may be prepared as a draft under the
  bound owner policy. **Provider send authority is still false.**
- `OWNER_REVIEW_REQUIRED` — the router already requires review, several inbound
  events are in one receipt, the draft mode was not preapproved, or the proposal
  is commercially sensitive.
- `SUPPRESS` — the upstream receipt is do-not-contact / terminal DNR for this
  action.
- `NO_ACTION` — upstream says wait, or the exact inbound event is already in the
  complete handled-event history.
- `ROUTE_REPAIR` — upstream reports a delivery-failure route-repair state and no
  stronger DNR blocks it.
- `HOLD` — scope, freshness, history, digest, or custody evidence is unsafe.

Every receipt remains side-effect-free. Even `DRAFT_ALLOWED` contains:

```json
{
  "provider_send_authorized": false,
  "new_thread_authorized": false,
  "pricing_authorized": false,
  "discount_authorized": false,
  "scope_expansion_authorized": false,
  "contract_authorized": false,
  "payment_authorized": false,
  "buyer_acceptance_inferred": false,
  "revenue_recognized": false
}
```

## Hard commercial boundary

Only four modes can ever be preapproved for factual draft creation in v1:

- `ROUTING_CONTEXT`
- `FIT_ANSWER`
- `CLARIFYING_QUESTION`
- `SCHEDULING_COORDINATION`

The following modes are hard-coded owner-review boundaries and cannot be placed
in `allowed_draft_modes` by input policy:

- `PRICING`
- `DISCOUNT`
- `SCOPE_CHANGE`
- `CONTRACT_TERMS`
- `PAYMENT`
- `ACCEPTANCE`
- `CREDENTIALS`
- `LEGAL_TERMS`

That distinction is deliberate. A human-routing acknowledgement such as “this
is worth getting in front of the right person” must not silently become a sales
acceptance, and a buyer asking about price must not let an unattended worker
invent or negotiate price.

## Inputs

### 1. Inbound-router receipt

Schema: `inbound-reply-router-receipt/v1`.

The guard independently verifies the router receipt SHA-256, the digest of its
relevant provider message IDs, exact false side-effect authority, and its bound
`offer_id`, counterparty, thread, owner, DNR flags, action, and evaluation time.
A tampered or authority-escalated upstream receipt is rejected structurally.

### 2. Owner policy

Schema: `commercial-reply-policy/v1`.

```json
{
  "schema": "commercial-reply-policy/v1",
  "policy_id": "policy-001",
  "offer_id": "offer-001",
  "counterparty": "buyer@example.com",
  "thread_id": "provider-thread-001",
  "owner_id": "Z-OWNER",
  "issued_at": "2026-09-13T09:50:00Z",
  "expires_at": "2026-09-13T11:00:00Z",
  "allowed_draft_modes": ["FIT_ANSWER", "CLARIFYING_QUESTION"]
}
```

Policy TTL is code-capped at seven days. Sensitive modes are rejected from the
policy rather than treated as a caller-controlled exception.

### 3. Reply proposal

Schema: `commercial-reply-proposal/v1`.

```json
{
  "schema": "commercial-reply-proposal/v1",
  "proposal_id": "proposal-001",
  "offer_id": "offer-001",
  "counterparty": "buyer@example.com",
  "thread_id": "provider-thread-001",
  "owner_id": "Z-OWNER",
  "inbound_message_id": "provider-inbound-001",
  "mode": "FIT_ANSWER",
  "body_sha256": "<lowercase sha256 of exact draft bytes>",
  "requested_at": "2026-09-13T10:01:00Z",
  "history_complete": true,
  "handled_inbound_message_ids": []
}
```

The handled-event history must explicitly be complete. Replaying a previously
handled provider message returns `NO_ACTION`. A positive draft path requires
exactly one relevant provider message in the upstream router receipt and that
message must equal `inbound_message_id`.

## Freshness and binding

A draft cannot be authorized when:

- policy/router/proposal disagree on offer, counterparty, thread, or owner;
- proposal predates policy issuance or exceeds policy expiry;
- the upstream router receipt is more than 15 minutes older than the proposal;
- the router receipt is more than five minutes in the proposal's future;
- handled-event history is incomplete;
- the exact inbound provider message is not bound by the router receipt;
- multiple relevant inbound events are collapsed into one would-be factual
  draft (owner review instead);
- upstream custody is `HOLD`, review-only, wait-only, route-failure, or
  do-not-contact.

All positive receipts bind `router_receipt_sha256`, `policy_sha256`,
`proposal_sha256`, `body_sha256`, and their exact commercial scope into a final
content-addressed `receipt_sha256`.

## CLI

```bash
python -m tools.commercial_reply_guard.guard \
  --router-receipt /path/router-receipt.json \
  --policy /path/policy.json \
  --proposal /path/proposal.json \
  --output /path/guard-receipt.json
```

Input files must be distinct ordinary files and the output cannot alias an
input. Output uses same-directory staging, `fsync`, and atomic replacement.

## Regression gate

```bash
python -m py_compile \
  tools/commercial_reply_guard/guard.py \
  tools/commercial_reply_guard/test_guard.py
python -m unittest -v tools.commercial_reply_guard.test_guard
python -O -m unittest -v tools.commercial_reply_guard.test_guard
```

The hostile suite covers all factual and sensitive modes, DNR/unsubscribe,
wait/auto-routing state, delivery failure, router HOLD/review, exact scope
binding, policy TTL/expiry, stale/future router evidence, incomplete history,
idempotent handled-message replay, unbound/multiple inbound events, upstream
receipt tampering, attempted upstream authority escalation, message-digest
mismatch, duplicate IDs, unknown fields, strict SHA-256, deterministic content
binding, atomic CLI publication, alias rejection, and duplicate JSON keys.
