# Hot-lead commercial owner decision gate

`owner_decision_gate.py` is the **pre-send, pre-commitment owner-ruling compiler** for live commercial threads.
It exists for the stage where a lead has already become commercially material — price/budget, paid scope, procurement/contract terms, or Bryce-attended time — and parallel workers must converge on **one** owner decision instead of sending overlapping messages or asking the owner the same question repeatedly.

The gate is intentionally narrower than the existing outbound-send guard:

1. it binds one decision to `mailbox + thread_id + controlling inbound event id + decision_type`;
2. it requires a complete, fresh provider snapshot whose **latest provider event is still the controlling inbound**;
3. it requires a complete shared prior-decision ledger snapshot before calling the decision unique;
4. it suppresses an exact repeat as `DUPLICATE_EXISTING` and fails closed if the same decision key is reminted with different payload/provider-generation facts;
5. it emits the exact provider evidence, prior offers/promises, evidenced amounts, deadlines, recommendation, and owner ruling needed as one deterministic Markdown decision brief;
6. it derives `owner_alert_lease_key = owner-decision-lease/v1/<decision_key>` so the coordination layer can atomically reserve the *owner alert itself* before notifying Bryce.

A `READY_FOR_OWNER_RULING` result means only: **this is one current, unique question that may attempt to acquire the owner-alert lease.** It is not approval and does not grant a provider side effect. Every receipt has `side_effects_authorized=false`.

After Bryce rules, any actual buyer/prospect outbound still must separately reacquire current provider/mailbox history and the canonical outbound atomic send lease immediately before the provider mutation. This module never sends email, creates calendar events, accepts commercial terms, captures payment, or recognizes revenue.

## Schemas

### Request — `owner-commercial-decision-request/v1`

Required identity and commercial context:

- `request_id`
- `mailbox`
- `thread_id`
- `inbound_event` with exact `event_id`, lowercase SHA-256, and zoned `observed_at`
- `decision_type`: `PRICE_BUDGET`, `PAID_SCOPE`, `PROCUREMENT_TERMS`, `CONTRACT_TERMS`, or `OWNER_TIME`
- `buyer_scope`
- `opportunity_id`
- `prior_offers[]`: amount in integer minor units, currency, state, exact evidence event
- `prior_promises[]`: bounded summary + exact evidence event
- `evidenced_amounts[]`
- `deadlines[]`
- `recommendation.action` and `.rationale`
- `ruling_needed`

The decision key intentionally excludes prose and price. Two workers describing the same mailbox/thread/inbound/decision-type differently therefore **collide on one key** instead of minting two owner questions.

### Provider snapshot — `owner-commercial-provider-snapshot/v1`

The adapter that actually reads Gmail/provider state supplies:

- `complete=true` only after the controlling thread/provider history query is complete;
- same `mailbox` and `thread_id`;
- `captured_at`;
- exact `latest_inbound`;
- exact `latest_provider_event`;
- a canonical `history_digest` over the adapter's retained thread history;
- `relationship_generation`;
- `relationship_disposition`: `ACTIONABLE`, `HOLD`, or `CLOSED`;
- `relationship_state` as the adapter's current descriptive state.

The compiler is fail closed when the snapshot is partial, stale, future-dated, refers to a different thread, is non-actionable, or has **any newer/different provider event** after the proposed controlling inbound.

### Prior decision ledger — `owner-commercial-decision-brief-set/v1`

```json
{
  "schema_version": "owner-commercial-decision-brief-set/v1",
  "complete": true,
  "briefs": []
}
```

`complete=false` (or omitting this file) forces `HOLD`. The adapter must populate `briefs` from the shared retained decision ledger, not from one worker's local memory. The embedded `receipt_digest` is tamper evidence only; it is not a signature or proof that an untrusted file came from Bryce.

## Decisions

- `READY_FOR_OWNER_RULING` — provider state is current and actionable; shared decision ledger is complete; no same-key prior decision exists. `owner_alert_allowed=true` means only that the caller may attempt the separate atomic owner-alert lease.
- `DUPLICATE_EXISTING` — the same decision key + request digest + provider binding + relationship generation was already compiled. Do not alert Bryce again.
- `HOLD` — missing/incomplete evidence, stale/new provider event, non-actionable relationship, chronology problem, or same-key conflicting prior artifact. Do not alert and do not send.

No decision grants buyer/prospect side effects.

## CLI

```bash
python -m tools.outbound_send_guard.owner_decision_gate \
  --request request.json \
  --provider-snapshot provider-snapshot.json \
  --prior-briefs decision-ledger-snapshot.json
```

The receipt is canonical JSON on stdout. Exit codes:

- `0` — `READY_FOR_OWNER_RULING`
- `3` — `DUPLICATE_EXISTING`
- `4` — `HOLD`
- `2` — invalid input/read failure

## Regression gate

```bash
python -m py_compile \
  tools/outbound_send_guard/owner_decision_gate.py \
  tools/outbound_send_guard/test_owner_decision_gate.py
python -m unittest -v tools.outbound_send_guard.test_owner_decision_gate
python -O -m unittest -v tools.outbound_send_guard.test_owner_decision_gate
```

The hostile suite covers incomplete provider history, newer provider events, stale/future snapshots, closed/HOLD relationship state, mailbox/thread mismatch, latest-inbound mismatch, exact decision dedupe, same-key payload/provider-generation conflict, tampered prior receipts, forged `side_effects_authorized=true`, duplicate JSON keys, non-finite JSON, boolean-as-integer amounts, uppercase/noncanonical SHA-256, naive timestamps, and CLI semantic exits.

## Authority ceiling

This is an internal evidence compiler, not an identity/authentication service. It does **not** prove that an input provider snapshot was honestly produced, that a prior-decision ledger came from a trusted store, or that Bryce approved anything. Those are adapter/storage/owner-authentication responsibilities. The module only makes supplied evidence mechanically strict, current, collision-resistant, replay-checkable, and explicit about what remains unauthorized.