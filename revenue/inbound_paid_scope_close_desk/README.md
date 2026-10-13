# Inbound paid-scope owner-close desk

Issue: `woahwhattheheck/commons#15130`

This module converts **retained evidence of genuine human inbound scope interest** into a deterministic internal owner-review packet. It exists to keep conversion work moving without recreating the collision failure mode where multiple swarm seats independently reply to the same hot lead.

The strongest result is `READY_FOR_OWNER_CLOSE`. That result is **not** permission to send anything. It means the internal packet is coherent enough for the owner to review. Immediately before an actual reply, a send-capable worker still has to refresh the route/prior-touch census, obtain or re-confirm the exact Muse single-writer election, and independently satisfy whatever outbound authority applies to the provider adapter.

## Truth boundary

`INTERNAL_OWNER_CLOSE_REVIEW_ONLY`

The compiler deliberately keeps all of these authority flags false:

- external email / DM / issue-comment / web-form send
- contract or signature authority
- buyer acceptance
- invoice authority
- payment authority
- cash or revenue recognition
- deployment
- scheduling

A Muse receipt means only: **this exact opportunity × action has a single selected writer for collision control**. It is never represented as proof that a message was sent, received, accepted, paid, or booked.

`evaluation_time` is an owner-supplied evaluation clock used for deterministic currentness checks. The packet says so explicitly; it does not represent that timestamp as provider-authenticated time. Source metadata is likewise `CURATED_RECEIPT_METADATA_NOT_LIVE_PROVIDER_AUTHENTICATED`. This compiler is an evidence organizer and close-review gate, not a live provider verifier.

## Decision states

| State | Meaning |
| --- | --- |
| `READY_FOR_OWNER_CLOSE` | Fresh provider-receipt-shaped human scope/positive event, clear route/collision state, current offer/evidence/qualification, and exact unexpired Muse selection all line up. Still internal-only. |
| `HOLD_SCOPE` | No fresh qualifying external-human scope/positive event. Auto-acks, support tickets, bounces, silence and ambiguous events never count as interest. |
| `HOLD_ROUTE` | Route, provider match, collision state or prior-touch state is not fresh/clear. |
| `HOLD_EVIDENCE` | Offer/capability/qualification evidence is stale, missing, expired or unsupported. |
| `HOLD_MUSE` | Exact current Muse single-writer selection is absent, expired or mismatched. |
| `HOLD_SYNTHETIC` | Fixture/demo input. Synthetic evidence can exercise code but can never become a live close-ready case. |
| `DNR` | A do-not-contact state exists. |

`PARTNER_ONLY` qualification may still reach owner review: it means a workshare close can be discussed, not that TJLabs may claim prime qualifications it does not hold.

## Input contract

The strict JSON schema includes:

- exact event identity (`provider`, conversation/message IDs, source/text SHA-256, observed time, sender role, event class);
- a source-bound current offer that remains `PROPOSED_NOT_ACCEPTED`;
- capability evidence with `VERIFIED | OWNER_ONLY | MISSING | EXPIRED | UNKNOWN` and public/private visibility;
- qualification status and gaps;
- route identity, canonical opportunity/action keys and collision state;
- exact Muse election identity, selected writer, opportunity/action keys and expiry;
- prior-touch/collision ledger state.

Unknown keys, duplicate JSON keys, floats/non-finite numbers, boolean-as-integer values, invalid timestamps, future evidence, duplicate evidence IDs and malformed hashes fail closed.

## CLI

```bash
python -m revenue.inbound_paid_scope_close_desk.engine compile \
  input.json \
  --packet close.packet.json \
  --markdown close.packet.md \
  --receipt close.receipt.json

python -m revenue.inbound_paid_scope_close_desk.engine verify \
  input.json close.packet.json close.packet.md close.receipt.json
```

Successful verification prints:

```text
EXACT_OWNER_CLOSE_MATCH
```

Compilation publishes all three outputs create-exclusively. It stages and `fsync`s complete bytes before hard-link publication, refuses existing/symlink outputs, preflights distinct paths, and rolls back files it published if a later publication step fails.

## Synthetic rehearsal

`demo/synthetic_inbound.json` is intentionally marked `"fixture": true`. Running the compiler on it must produce `HOLD_SYNTHETIC`. The committed fixture is **not** evidence of a real lead, buyer, offer acceptance, payment, or revenue.

## Hostile coverage

The focused suite covers, among other predecessors:

- auto-ack / support-ticket / silence promoted to human interest;
- stale/future event and evidence timestamps;
- curated-export text relabeled as provider human evidence;
- live fixture promotion;
- DNR and active-other-owner collision handling;
- provider mismatch and stale routes;
- missing/expired capability evidence and unsupported qualification;
- exact Muse opportunity/action mismatch and expiry;
- private evidence leakage into buyer-neutral Markdown;
- duplicate JSON keys, floats, NaN/Infinity and bool-as-int;
- one-byte input drift plus packet/Markdown/receipt tampering;
- partial/overwrite CLI publication;
- merge/payment-link style pseudo-events;
- authority flags accidentally becoming positive.

Run:

```bash
python -m py_compile revenue/inbound_paid_scope_close_desk/engine.py test_inbound_paid_scope_close_desk.py
python -m unittest -v test_inbound_paid_scope_close_desk.py
python -O -m unittest -v test_inbound_paid_scope_close_desk.py
```
