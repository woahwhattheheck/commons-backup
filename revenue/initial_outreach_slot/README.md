# Initial outreach slot

This package closes the seconds-apart duplicate **first-contact** race across swarm workers.
It composes three landed controls:

- `revenue.commercial_opportunity_custody`: current WHOLE / bounded `outreach` custody;
- `tools.outbound_send_guard.capability_lease`: v2 live Git-ref ownership plus private-capability possession;
- `revenue.opportunity_identity_alias`: independently retained canonical opportunity key.

Original product/source: **Z-PascalEstuary-2210-S4Q8 (`ZPE-S4Q8`)**. Recovery on
current main closes SOURCE REDs **ZMK-Q9V4** (no `repr`/`str` on callback return)
and **ZHBW-R7C4** (canonical key from the landed alias registry, not
caller-authored `opportunity_id`). It consumes `#15026` / `revenue.opportunity_identity_alias`
and does **not** remint that registry.

The terminal exclusion key is the registry's `canonical_opportunity_key` plus
repo and buyer. Two workers describing the same retained pursuit as
`rfp-04254` vs `lacsd-04254`, or buyer-site vs procurement-portal authority,
therefore race one immutable ref when the registry maps those aliases to one
key. Unresolved/empty-registry observations fail closed before any Git mutation
or callback. Caller-supplied keys and alias maps are rejected. Distinct retained
keys at the same buyer remain independently contactable. Generation 1 of the
registry is empty by design, so live first-contact stays HOLD until reviewed
facts exist.

```text
refs/tags/initial-outreach-v1/<sha256({schema, action, repo, buyer_scope, canonical_opportunity_key})>
```

## Provider-bound execution, not a bearer receipt

`execute_initial_outreach(..., send_once=<zero-arg callback>)`
accepts a zero-argument `send_once` callback. This boundary guarantees **one
Python callback invocation**, not one unconstrained provider mutation inside an
arbitrary callback. The callback is invoked only after all of these conditions
hold in the same invocation:

1. `resolve_current(...)` against the co-located alias registry returns exact `RESOLVED` with one canonical key (no caller registry/path selector);
2. live custody says the exact actor/operation owns WHOLE or `outreach`;
3. the v2 lease receipt is structurally valid and its repo/buyer/claimant bind to that opportunity/actor;
4. `capability_lease.verify_possession(...)` proves the private capability and current live v2 ref/tag;
5. a second custody read proves no transfer/release occurred during lease verification;
6. the canonical-key slot is absent;
7. this invocation creates the annotated audit tag and wins create-once creation of the canonical slot ref (or immediate same-call readback proves an indeterminate create created this exact tag);
8. a third custody read proves no transfer/release raced slot consumption.

Only then is `send_once()` called, synchronously and exactly once by this boundary.

No serializable result ever contains `external_send_authorized=true`. The
callback return is discarded without `repr`, `str`, serialization hooks, or a
correlation digest (ZMK-Q9V4). Durable tag metadata also fixes
`external_send_authorized=false` and contains no raw capability, recipient
address, subject/body, price, provider message ID, acceptance, payment, or
revenue assertion.

If `send_once()` raises—or the process dies after the slot is consumed—the slot
remains consumed. The result is reconciliation/DNR-only. Calling this module
again never invokes another initial-send callback. This deliberately prefers a
potentially lost outreach attempt over duplicate first contact.

## Result semantics

- `PROVIDER_CALLBACK_RETURNED`: slot consumed and callback returned normally. This does **not** infer provider delivery/completion or mint send authority.
- `SEND_OUTCOME_UNKNOWN`: callback was invoked but raised. Slot remains consumed; no retry authority.
- `HOLD`: callback was not invoked. `HOLD_UNRESOLVED_ALIAS` means the landed registry has no independently retained key. `HOLD_ALREADY_CONSUMED` means a prior invocation already owns/burned first contact.

Every result has:

```json
{"external_send_authorized":false,"provider_send_completed":false,"replay_or_retry_authorized":false}
```

`inspect_initial_outreach(...)` is read-only DNR/reconciliation evidence. It
resolves the same canonical key, validates live slot ref -> annotated tag ->
metadata/target/tagger, and never authorizes send.

## Validation

```bash
python -m py_compile revenue/initial_outreach_slot/slot.py revenue/initial_outreach_slot/test_slot.py
python -m unittest -v revenue.initial_outreach_slot.test_slot
python -O -m unittest -v revenue.initial_outreach_slot.test_slot
python -m unittest -v test_initial_outreach_slot
python -O -m unittest -v test_initial_outreach_slot
```

Hostiles cover price/offer aliasing, opportunity-id and authority-scope aliases
of one retained key, distinct retained keys at one buyer, unresolved/empty
registry, self-authored alias maps and caller keys, same-holder replay,
copied/wrong private capability, buyer/repo/claimant mismatch, custody transfer
before and after slot consume, concurrent existing ref, provider uncertainty,
same-call indeterminate recovery, callback exception burn-without-retry,
callback-return `__repr__` never executing, internal double-send not minting
send authority, raw-capability/result privacy, receipt tamper, and strict
inspection of tampered/duplicate-key metadata.
