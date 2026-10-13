# Route-aware outbound guard composition

`route_guard.py` composes two already-landed read-only authorities:

1. `guard.py` decides buyer/offer dedupe, cooldown, hard-DNR, and reply-only state from complete mailbox + Slack evidence.
2. `route_lifecycle.py` classifies whether the latest exact provider-message/email route is blocked, held, delivered, or unconfirmed from route evidence.

The purpose is adoption, not another classifier. A hard delivery failure must not be left in a sidecar that a later outbound worker can forget to consult.

## Fail-closed composition

The composer first recomputes the ordinary outbound guard receipt from the supplied intent/evidence. It then mirrors the base guard's exact outbound ordering across mailbox and Slack rows: `(observed_at, source_ref)`.

When the winning base-guard outbound is a mailbox row, its message id is the route target directly. When the winning row is a Slack `sent` event, that event must carry an explicit `provider_message_id` that resolves to a same-recipient outbound mailbox row. This prevents equal-time or delayed-Slack evidence from borrowing the route lifecycle of a different send.

When the base guard is send-capable (`ALLOW_NEW` or `REPLY_ONLY`) and there is a prior outbound:

- route evidence is mandatory;
- the latest logical outbound must resolve to an exact provider-mailbox message id, otherwise the result is `HOLD`;
- route `recipient`, `provider_message_id`, and `sent_at` must match that provider row;
- the route `sent_at` binds to provider-mailbox send time even when a source-linked Slack receipt was recorded later;
- route `as_of` must equal the base guard `generated_at`, preventing an older pre-DSN lookup from being reused against a fresher outbound snapshot;
- caller-supplied `DELIVERED` and `UNCONFIRMED` lifecycle results do **not** satisfy the required route check and therefore return `HOLD` until independent complete-snapshot authority is implemented.

Decision composition is monotone:

| Base guard | Caller route lifecycle | Final |
|---|---|---|
| any | `BLOCK_ROUTE` | `DO_NOT_RESEND` unless already stricter |
| `ALLOW_NEW` / `REPLY_ONLY` | `HOLD_ROUTE` | `HOLD` |
| `ALLOW_NEW` / `REPLY_ONLY` | `DELIVERED` / `UNCONFIRMED` | `HOLD` pending independent snapshot authority |
| `HOLD` / `DO_NOT_RESEND` | any | never promoted |

Missing required route evidence returns `HOLD`, not `ALLOW_NEW`. A latest Slack `sent` row without a source-linked provider-mailbox message also returns `HOLD`, because no source-bound route lifecycle can be attached to it.

The composed receipt exposes the exact `latest_outbound_ref` and `latest_outbound_source` used for that binding. When caller-supplied nonblocking lifecycle evidence is the only route evidence for a required check, the composed authority is downgraded from `complete` to `partial` and the receipt records that independent complete-snapshot authority is missing. The final receipt always sets `side_effects_authorized=false`. It is evidence for a separately authorized sender, never an email-send capability.

## Complete-snapshot authority boundary

`route_lifecycle.py` validates the internal structure, exact route identity, event timestamps, event source hashes, and the caller's `complete`/`next_cursor` claim. Those properties are useful for classification, but they do **not** independently prove that the provider query was exhaustive. A caller can otherwise construct a syntactically valid `complete=true` object while omitting a complaint, unsubscribe, DSN, or delivery event.

Therefore the current composer treats lifecycle evidence asymmetrically:

- `BLOCK_ROUTE` and `HOLD_ROUTE` may demote because accepting extra restrictive evidence cannot grant outbound authority;
- `DELIVERED` and `UNCONFIRMED` are descriptive only when supplied by the caller and cannot preserve a send-capable base decision;
- a forged empty `complete=true` snapshot, a fabricated delivered row, omission of one blocking event, or replay of an older snapshot cannot yield `ALLOW_NEW`/`REPLY_ONLY` through this composer.

Restoring nonblocking route results as send-satisfying evidence requires a separately trusted provider-backed snapshot generator/retainer that commits at least the query scope, completeness, `as_of`, exact provider message, exact event set/root, and a freshness/generation identity that cannot be self-minted by the caller. Until that authority exists, fail closed.

## DSN authority boundary

This composer recomputes `route_lifecycle.evaluate()` from raw route-lifecycle evidence and binds its source-evidence digest. It does **not** accept a caller-claimed route receipt.

For DSN events, use the existing source-binding path before insertion into route-lifecycle evidence:

```python
from tools.outbound_send_guard.dsn_authority import authoritative_event
```

`dsn_authority.authoritative_event()` recomputes the normalized DSN event from independently supplied raw MIME + binding inputs. `route_guard.py` deliberately does not reimplement that parser or weaken its owner boundary. DSN source binding and route-query completeness are separate trust questions: source-bound events do not make an omitted-event query complete.

## CLI

Brand-new recipient with no prior outbound:

```bash
python -m tools.outbound_send_guard.route_guard \
  --intent intent.json \
  --evidence outbound-evidence.json \
  --out composed-receipt.json
```

Prior outbound / reply lane:

```bash
python -m tools.outbound_send_guard.route_guard \
  --intent intent.json \
  --evidence outbound-evidence.json \
  --route-evidence route-evidence.json \
  --out composed-receipt.json
```

Exit codes preserve the ordinary guard semantics: `0 ALLOW_NEW`, `3 REPLY_ONLY`, `4 HOLD`, `5 DO_NOT_RESEND`, `2 invalid or uncomposable evidence`.

## Operational adoption rule

For any worker that can cross an outbound email provider boundary, consume the composed receipt rather than `guard.py` alone once a recipient has prior outbound evidence. Do not translate a DSN into permission to discover or contact an alternate person/address. `BLOCK_ROUTE` and `HOLD_ROUTE` only remove authority; an alternate route must independently pass the ordinary guard and any applicable lease/owner gates.

Do not treat a route-lifecycle receipt or its `source_evidence_sha256` as proof of provider-query completeness. Until the independent complete-snapshot authority described above exists, a composed receipt with required caller-supplied `DELIVERED`/`UNCONFIRMED` evidence remains `HOLD`.

## Regression gate

```bash
python -m py_compile \
  tools/outbound_send_guard/route_guard.py \
  tools/outbound_send_guard/test_route_guard.py
python -m unittest -v tools.outbound_send_guard.test_route_guard
python -O -m unittest -v tools.outbound_send_guard.test_route_guard
```

The focused suite covers hard `5.1.1`, non-allowlisted permanent `5.4.1`, temporary `4.2.2`, caller-supplied delivered/unconfirmed fail-closed controls, forged empty-complete snapshots, omitted blocking events, stale snapshot replay, missing route evidence, Slack-only latest sends, unresolved Slack provider ids, same-time Slack/mail identity collisions, delayed source-linked Slack receipts, exact provider-message binding, route-recipient/time/snapshot mismatches, latest-of-two provider sends, reply-only demotion, no-promotion invariants, deterministic receipts, input immutability, and CLI exit behavior.
