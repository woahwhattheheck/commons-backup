# Commercial Deal Room

`commercial-deal-room/v1` is a buyer-neutral, offline commercial-lifecycle compiler for fixed-price service/software offers. It exists to answer one operational question without lying: **what owner-reviewed action is justified by the evidence we actually have?**

It deliberately separates facts that fleets commonly collapse:

- an offer or proposal **sent** is not buyer acceptance;
- a configured Stripe/payment route is not a payment;
- a payment request sent is not settlement;
- a merged/build artifact is not delivery or fulfillment acceptance;
- settlement evidence is not accounting revenue recognition;
- DNR/rejection is not reopened by another internal worker deciding to try again.

## Contract

A packet binds one `buyer_id + opportunity_id + offer_id` to immutable offer terms and append-only evidence events. Every event repeats the full identity, source reference and source digest. Exact event-ID replay collapses; changed same-ID payloads HOLD. Provider message IDs cannot be reused across different facts. Buyer replies must reference earlier outbound evidence and occur later. Proposals are revisioned and acceptance binds the latest proposal digest. Payment requests bind the active payment route and accepted offer. Settlement/reversal evidence is reconciled in exact integer minor currency units. Fulfillment send/acceptance must bind a specific artifact event.

Current-time evaluation is process-owned by the CLI. `verify` first proves historical board bytes at their recorded evaluation time, then recompiles current state; an old OFFER_READY board cannot silently remain current after expiration.

## Stages / owner-review actions

Representative projections include:

| Stage | Action |
|---|---|
| `OFFER_READY` | `OWNER_SEND_REVIEW` |
| `AWAITING_BUYER` | `WAIT_BUYER` |
| `BUYER_INTEREST` | `PREPARE_SCOPE` |
| `PROPOSAL_SENT` | `WAIT_BUYER` |
| `BUYER_ACCEPTED` | `ESTABLISH_PAYMENT_ROAD` |
| `PAYMENT_ROAD_READY` | `ASK_FOR_PAYMENT` |
| `AWAITING_SETTLEMENT` | `WAIT_SETTLEMENT` |
| `FUNDED_TO_START` | `FULFILL` |
| `FULFILLMENT_READY` | `OWNER_DELIVERY_REVIEW` |
| `DELIVERED` | `WAIT_BUYER_ACCEPTANCE` |
| `FULFILLMENT_ACCEPTED_BALANCE_DUE` | `ASK_FOR_BALANCE` |
| `CLOSED_SETTLED` | `CLOSE_SETTLED` |
| `DNR` | `WAIT_DNR` |
| `HOLD` | `INVESTIGATE_EVIDENCE` |

No action is an external-action authorization. They are owner-review queue labels only.

## Truth / authority ceiling

This package is intentionally **not** a provider-authentication primitive. A SHA-256 digest proves byte identity, not that Gmail, Stripe, a buyer, a bank, or any other actor actually produced those bytes. Integrations must acquire external evidence through a separately trusted provider path. The compiler and receipt verifier do not authorize email/Slack sends, payment/wallet mutations, deployment, contract acceptance, or accounting revenue recognition.

`CLOSED_SETTLED` means: the supplied lifecycle evidence contains explicit buyer acceptance, qualifying settlement evidence, fulfillment send evidence, and explicit buyer fulfillment acceptance with no active hold. It still does not mean GAAP/IFRS revenue recognition.

## CLI

```bash
python -m revenue.commercial_deal_room.cli compile deal.json --format json
python -m revenue.commercial_deal_room.cli compile deal.json --format markdown
python -m revenue.commercial_deal_room.cli verify deal.json board.json
```

Ingress rejects duplicate JSON keys, non-regular final files, oversized inputs, and final-component symlinks where `O_NOFOLLOW` is available. The engine rejects unknown keys and unsupported event shapes.

## Validation

```bash
python -m unittest revenue.commercial_deal_room.test_engine revenue.commercial_deal_room.test_cli
python -O -m unittest revenue.commercial_deal_room.test_engine revenue.commercial_deal_room.test_cli
python -m revenue.commercial_deal_room.acceptance
```
