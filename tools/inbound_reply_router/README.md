# Inbound Reply Router

`inbound_reply_router` is a fail-closed custody layer for commercial replies.

The outbound send guard answers **whether a new outbound may be attempted**. This
tool answers a different question after a send already exists:

> Given a complete, fresh provider snapshot and a complete ownership snapshot,
> what owner queue should a classified inbound event enter?

It deliberately does **not** read free-form email bodies, send mail, authorize a
reply, move money, create a contract, or recognize revenue. Human/provider
classification happens before this tool. The router validates that evidence,
binds it to one offer/thread/route/owner, rejects ambiguous state, and emits a
deterministic content-addressed receipt.

## Why this exists

A sales feed can contain many terminal `SENT / DO NOT RESEND / reply custody
retained` records. Once replies arrive, these failure shapes matter:

- an automated acknowledgement is mistaken for buyer interest;
- an out-of-office response is treated as a qualified reply;
- a delivery failure is retried to the same broken route;
- a support "forwarded to the right team" acknowledgement is called acceptance;
- two peers both believe they own the same reply;
- a replayed provider message creates duplicate work;
- a stale or partial mailbox query silently authorizes action;
- a human reply is attached to the wrong offer/thread/route;
- `YES` is inflated into contract, payment, or revenue.

The router closes those ambiguity gaps without becoming an auto-sender.

## Schemas

### Context — `inbound-reply-context/v1`

```json
{
  "schema": "inbound-reply-context/v1",
  "offer_id": "WYOMING-INBRE-EVIDENCE-RAIL-...",
  "counterparty": "buyer@example.org",
  "thread_id": "provider-thread-id",
  "owner_id": "Z-SOMEOWNER",
  "prior_outbound_message_id": "provider-message-id",
  "prior_outbound_observed_at": "2026-09-13T08:18:23Z"
}
```

The context is one already-sent offer and one canonical reply owner.

### Evidence — `inbound-reply-evidence/v1`

```json
{
  "schema": "inbound-reply-evidence/v1",
  "captured_at": "2026-09-13T08:29:30Z",
  "provider_query_complete": true,
  "ownership_query_complete": true,
  "events": [
    {
      "message_id": "provider-inbound-id",
      "thread_id": "provider-thread-id",
      "counterparty": "buyer@example.org",
      "observed_at": "2026-09-13T08:25:00Z",
      "offer_id": "WYOMING-INBRE-EVIDENCE-RAIL-...",
      "classification": "HUMAN_QUESTION",
      "classified_by": "human_operator",
      "classifier_id": "operator-id",
      "new_route": null
    }
  ],
  "owner_bindings": [
    {
      "owner_id": "Z-SOMEOWNER",
      "offer_id": "WYOMING-INBRE-EVIDENCE-RAIL-...",
      "thread_id": "provider-thread-id",
      "status": "ACTIVE",
      "observed_at": "2026-09-13T08:29:00Z"
    }
  ]
}
```

The evidence source must explicitly report whether the provider and ownership
queries were complete. A partial or stale snapshot does not degrade into a
best-effort decision; it produces `HOLD`.

## Classifications

Human classifications require `classified_by=human_operator` and a non-empty
`classifier_id`.

| Classification | Router behavior |
| --- | --- |
| `HUMAN_INTERESTED` | `OWNER_REPLY_REQUIRED` |
| `HUMAN_QUESTION` | `OWNER_REPLY_REQUIRED` |
| `HUMAN_ROUTE_CHANGE` | `OWNER_REPLY_REQUIRED`, preserving only the explicitly supplied candidate route |
| `HUMAN_DECLINED` | `CLOSE_DO_NOT_CONTACT` for this offer/route |
| `HUMAN_UNSUBSCRIBE` | hard `CLOSE_DO_NOT_CONTACT` |
| `HUMAN_ROUTING_ACK` | `WAIT_NO_ACTION`; routing acknowledgement is not buyer interest |
| `HUMAN_OTHER` | `OWNER_REVIEW_REQUIRED` |

Provider classifications require `classified_by=provider` and no classifier
identity.

| Classification | Router behavior |
| --- | --- |
| `AUTO_ACK` | `WAIT_NO_ACTION` |
| `OUT_OF_OFFICE` | `WAIT_NO_ACTION` |
| `DELIVERY_FAILURE` | `ROUTE_REPAIR_REQUIRED`; same-route resend remains unauthorized |
| `DELIVERY_DELAY` | `WAIT_NO_ACTION` |
| `UNKNOWN` | `HOLD` |

A provider delivery failure and a human reply in the same bound evidence
snapshot conflict and therefore `HOLD`.

An unsubscribe is not silently overridden. If a later human event appears after
an unsubscribe, the tool returns `HOLD` so a human can decide whether the later
message is an explicit, valid re-engagement.

## Fail-closed invariants

The router rejects or holds on:

- incomplete provider or ownership queries;
- stale or materially future-dated snapshots;
- zero, multiple, duplicate, or mismatched active owners;
- evidence rows outside the bound offer/thread/counterparty;
- conflicting copies of one provider `message_id`;
- provider events materially later than the snapshot/evaluation clock;
- human classifications without a named human classifier;
- provider classifications falsely presented as human review;
- route-change classifications without an explicit syntactically valid new
  email route;
- an outbound recorded after a known earlier unsubscribe;
- unknown/unclassified inbound evidence.

Exact duplicate provider rows are idempotently deduplicated by message ID. A
duplicate ID with different semantics fails closed.

## Authority boundary

Every receipt contains:

```json
{
  "authority": {
    "owner_queue_custody_only": true,
    "side_effects_authorized": false,
    "reply_send_authorized": false,
    "resend_authorized": false,
    "payment_authorized": false,
    "contract_authorized": false,
    "revenue_recognized": false,
    "buyer_acceptance_inferred": false
  }
}
```

`OWNER_REPLY_REQUIRED` means **the canonical human owner should inspect and
handle the reply**. It is not permission for an unattended sender.

`HUMAN_INTERESTED` means **interest**, not a sale. A contract, purchase order,
verified payment, or other applicable commercial acceptance still needs its own
authoritative evidence and workflow.

No raw message body is needed by this tool.

## CLI

```bash
python tools/inbound_reply_router/router.py \
  --context /path/to/context.json \
  --evidence /path/to/evidence.json \
  --evaluated-at 2026-09-13T08:30:00Z \
  --output /path/to/reply-receipt.json
```

The evaluation timestamp is explicit so identical inputs produce identical
receipts. Output is written with same-directory temporary-file + `fsync` +
atomic replace.

The CLI exits `0` after producing a receipt, including a fail-closed `HOLD`.
Structurally invalid JSON/schema/time/classification input exits `2`.

## Validation

From the repository root:

```bash
python -m unittest -v tools.inbound_reply_router.test_router
python -O -m unittest -v tools.inbound_reply_router.test_router
python -m py_compile \
  tools/inbound_reply_router/router.py \
  tools/inbound_reply_router/test_router.py
```

The hostile suite covers incomplete/stale/future snapshots, ownership
collisions, scope mismatches, replay dedupe and replay conflicts, auto-acks,
OOO, bounces, unknown evidence, route changes, declines/unsubscribes, historical
DNR conflicts, deterministic receipts, atomic publication, and the CLI path.
