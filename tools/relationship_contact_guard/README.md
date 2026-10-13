# Relationship Contact Guard

`relationship_contact_guard` is a **coordination diagnostic**, not an outbound sender and not an authorization surface.

It closes a fleet-level anti-spam gap that exact-recipient single-writer locks cannot close by themselves: two workers may hold different operation keys or routes for the same organization/opportunity and each can appear locally clean while still hitting one hot relationship too close together.

## What it binds

A packet contains one proposed contact and an ordered retained event history. The guard binds canonical counterparty, opportunity, route, purpose, evaluation timestamp, provider message/thread identifiers, human-response lineage, human-negative scope, explicit reopen target, and event chronology. It emits canonical JSON plus a SHA-256 **semantic consistency** receipt; that hash is not a signature and does not authenticate clock or provider provenance.

The compiler detects, among other cases:

- same counterparty contacted recently through a different route or operation key;
- same opportunity/purpose contacted within a longer pursuit window;
- exact route/purpose provider-SENT with no later resolving event (`HOLD_EXACT_DNR`);
- a route with a retained hard-bounce (`HOLD_DEAD_ROUTE`) without converting that transport failure into organization rejection;
- explicit human negative/opt-out at route-purpose or whole-counterparty scope;
- a genuine retained human reply, which converts the whole counterparty relationship lane to inbound review rather than fresh outbound, including later/different opportunities until a separate explicit relationship-handling policy says otherwise;
- future-dated, reordered, duplicate, semantically duplicated under reminted source ids, orphaned, cross-counterparty, noncanonical, oversized, over-deep, unsafe-integer, or malformed evidence.

Callers may lengthen cooldowns but cannot weaken the code-owned floors: six hours for counterparty contact and 72 hours for same-opportunity/same-purpose pursuit contact. Direct Python objects are admitted through one detached bounded JSON snapshot before canonical serialization: exact integers are limited to ±(2^53−1), canonical bytes to 1 MiB, nesting to 64 levels, and total JSON work nodes to 100,000 with dictionary keys and values both charged. Container cardinality is fenced against the remaining node budget before child traversal/copy, and canonical string/key bytes are charged incrementally, so an over-budget direct object is rejected before the full value reaches the private canonical encoder. `ensure_ascii=True` escape accounting includes DEL (`U+007F`) and all non-ASCII code points at their exact canonical escape width. Only the admitted detached generation is then canonicalized. Boundary failures normalize to `GuardError` rather than leaking interpreter `ValueError`/`RecursionError`.

## Response lineage and reopen semantics

A bounce or human response is accepted only when its `in_reply_to_message_id` refers to an earlier retained `PROVIDER_SENT` **and** its counterparty, opportunity, route, purpose, and optional provider thread exactly match that send. A response cannot be transplanted from another opportunity or route merely because a provider message id exists.

`HUMAN_REOPEN` is not a generic "relationship is clear" signal. It must carry:

- `in_reply_to_message_id`;
- `reopens_event_id` naming an earlier retained `HUMAN_NEGATIVE`;
- `scope` equal to that negative's scope;
- the exact counterparty/opportunity/route/purpose/message lineage of that negative.

Only that explicitly referenced negative is reopened. If multiple negatives are retained, every unreopened negative remains active; reopening a newer one cannot silently erase an older opt-out.

A retained hard bounce also remains transport-dead evidence even if later contradictory human-shaped evidence exists for the same send.

## Semantic duplicate fence

Source ids are not allowed to multiply evidence. Every normalized event receives a canonical semantic identity that excludes `event_id` and `provider_message_id` while retaining kind, timestamp, counterparty, opportunity, route, purpose, thread, scope, reply lineage, and reopen target when present. A second row with the same semantic identity is rejected even if those source ids were reminted. This is deliberately conservative: if two purported provider sends are indistinguishable after stripping caller-remintable source ids, the anti-spam guard does not assume they are separate sends.

## Process-owned currentness and retained verification

Packets do **not** carry a caller-controlled `now`. `compile_guard()` samples current UTC directly inside the public compiler and retains the exact whole-second `evaluated_at` in a `PROCESS_UTC_SNAPSHOT` artifact. This removes the direct candidate-clock attack.

The retained artifact deliberately does **not** claim that its clock provenance is authenticated. Its truth surface sets `evaluation_time_process_origin_authenticated=false` and `retained_replay_establishes_currentness=false`. A SHA-256 receipt can prove semantic consistency with retained bytes, not that the timestamp originally came from a trusted clock.

`verify_guard()` therefore performs two separate operations:

1. It checks the retained artifact/receipt at the retained timestamp, rejecting a future-dated snapshot, while explicitly returning `retained_time_process_origin_verified=false` and `retained_status_is_current=false`.
2. It samples fresh process UTC and recompiles the same retained packet as `PROCESS_UTC_VERIFY_FRESH`. That fresh decision is returned separately in the verification result.

The fresh decision still cannot prove the retained packet complete or provider state current; those truths stay false and external contact still requires a fresh provider/Slack census plus Muse gating.

## Truth boundary

Every artifact builds its authority map from source-literal false values. The exported `AUTHORITY` object is compatibility/documentation only and is not used to mint semantic output. Ordinary mutation or rebinding of that module attribute cannot widen compile or verify results.

These fields are always false:

- `send_authorized`
- `muse_authorized`
- `provider_send_proven`
- `buyer_acceptance_proven`
- `contract_proven`
- `payment_proven`
- `cash_proven`
- `revenue_recognized`

`NO_CONFLICT_FOUND` means only **no conflict was found in the supplied retained packet at that decision's evaluation time**. The retained snapshot does not authenticate the process origin of its own timestamp, and neither compile nor verify proves the packet complete or authenticates current provider state. Before external mutation, the executor still needs a fresh Slack + provider census and the session-bound Muse lease/consume/GO protocol. A HOLD here cannot be overridden by treating another coordination receipt as send authority.

## CLI

```bash
python tools/relationship_contact_guard/guard.py compile packet.json artifact.json
python tools/relationship_contact_guard/guard.py verify packet.json artifact.json
```

The packet shape is intentionally small:

```json
{
  "candidate": {
    "counterparty_id": "example.com",
    "opportunity_id": "example-rfp-1",
    "route": "sales@example.com",
    "purpose": "paid-qa-workshare"
  },
  "events": []
}
```

Provider sends require `provider_message_id`. Bounces and human responses must reference an earlier retained provider send through `in_reply_to_message_id`. Human negative events bind `scope` as either `ROUTE_PURPOSE` or `COUNTERPARTY`; reopen events additionally bind the exact prior negative through `reopens_event_id`.

## Proof

The retained root suite exercises strict JSON ingress, retained-time receipt replay, cross-route and cross-key collisions, route-scoped bounces, response opportunity/route/purpose/thread transplant rejection, exact negative-to-reopen binding, packet-transplant rejection, Unicode/noncanonical identifiers, cooldown-floor protection, future/reordered/duplicate evidence, CPython large-integer parser normalization plus direct-API huge-integer/depth/size containment, pre-traversal oversized-list/dict node fences, pre-serializer oversize-string rejection including `ensure_ascii` DEL-escape accounting, multiple-negative reopen isolation, hard-bounce precedence, changed-source-id semantic duplicates across sends/replies/negatives/reopens, future self-resealed snapshot rejection, old self-resealed snapshot truth degradation plus fresh re-evaluation, process-clock callback injection resistance, and source-literal hard-false authority under ordinary module rebinding. The same suite is required under normal Python and real `python -O`.
