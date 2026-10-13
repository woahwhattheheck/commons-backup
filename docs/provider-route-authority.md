# Provider-route authority control

This package compiles a caller-supplied evidence packet into one deterministic, fail-closed outreach state. It **does not send anything** and grants no external-send, Muse-request, provider-mutation, payment, contract, or revenue authority.

The operating problem is simple: coordination state can say a route is clear while a mailbox/provider already has a SENT receipt, delivery-status notification, timeout, or human reply. A second writer that trusts only stale coordination can duplicate contact or start route-spraying. This compiler gives asserted provider/mailbox events precedence over asserted coordination intent, while also making the trust boundary explicit: event source labels in the JSON packet are **caller asserted and unauthenticated**. A live Slack/Muse/provider re-census is still required before any external action.

## Decision states

| State | Meaning |
| --- | --- |
| `CANDIDATE_ONE_SEND` | The supplied packet has no modeled hold and contains post-TAKE route verification plus Muse clearance. This is a candidate for a fresh live re-census, **not send authority**. |
| `HARD_DNR` | The exact subject contains an asserted provider-SENT event. Wait for a genuine state change and verify live. |
| `DEAD_ROUTE` | The route contains an asserted hard-bounce event. A bounce is **not** permission to choose another address. |
| `HOLD_UNKNOWN` | Evidence is incomplete, delivery is uncertain, another purpose/route is already active, or the org-level route-spray guard is engaged. |
| `INBOUND_ONLY` | An asserted human reply/rejection exists for the organization; automated follow-up candidacy stops. |

Every receipt includes `evidence_trust: CALLER_ASSERTED_UNAUTHENTICATED` plus an `authority` block whose external-send, Muse-request, provider-mutation, payment-mutation, and revenue-recognition fields are all `false`.

## Precedence

1. Any same-organization human reply/rejection → `INBOUND_ONLY`.
2. Any hard bounce on the exact route, even for another purpose → `DEAD_ROUTE`.
3. Two or more distinct hard-bounced routes for the organization → `HOLD_UNKNOWN` / `ROUTE_SPRAY_GUARD`.
4. Soft bounce/provider timeout on the route → `HOLD_UNKNOWN`.
5. Provider SENT on the exact route and purpose → `HARD_DNR`.
6. Provider SENT on the same route for another purpose → `HOLD_UNKNOWN`.
7. Provider SENT on another route for the same organization → `HOLD_UNKNOWN` rather than silent fanout.
8. Only after all modeled holds are absent may `SLACK_TAKE + ROUTE_VERIFIED + MUSE_CLEAR` produce `CANDIDATE_ONE_SEND` for live re-verification.

`MUSE_CLEAR` and `ROUTE_VERIFIED` must be **strictly later** than the exact subject's `SLACK_TAKE`; timestamp ties fail closed. A later Muse label cannot override provider/mailbox hold state.

## Evidence model

Each event binds:

- immutable `event_id`;
- event `kind` and its required source label (`SLACK`, `MUSE`, `PUBLIC_EVIDENCE`, `PROVIDER`, or `MAILBOX`);
- timezone-aware timestamp, canonicalized to UTC;
- organization, purpose, route type, and route;
- an append-only evidence reference.

The parser rejects duplicate JSON keys, floats, duplicate event IDs, source/kind label mismatches, malformed emails, naive timestamps, and unexpected fields. Input events are canonicalized before SHA-256 receipt hashing, so packet order and equivalent timezone offsets cannot change the decision or digest.

The source label is structural validation only; it is not cryptographic provenance. A caller can still fabricate an otherwise well-formed packet, which is why `CANDIDATE_ONE_SEND` never sets `external_send_authorized=true`.

## CLI

```bash
python -m revenue.provider_route_authority.cli compile INPUT.json > RECEIPT.json
python -m revenue.provider_route_authority.cli verify INPUT.json RECEIPT.json
```

Before any real outbound action, independently re-check the live coordination claim, current Muse adjudication, route evidence, and mailbox/provider state. After any attempted send or newly observed event, append the evidence and recompile.

## Synthetic route-spray example

`revenue/provider_route_authority/fixtures/two-hard-bounces.json` contains two different hard-bounced mailboxes for one synthetic organization plus otherwise-valid coordination gates. It compiles to `HOLD_UNKNOWN` with `ROUTE_SPRAY_GUARD`, proving that two transport failures cannot be transformed into permission to try a third address.
