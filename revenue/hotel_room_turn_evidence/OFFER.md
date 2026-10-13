# Commercial Scope — Hotel Room-Turn Evidence Pilot

## Fixed offer

**$2,500 USD — one property, seven calendar days.**

The pilot demonstrates a bounded evidence-to-room-readiness workflow using agreed de-identified fixtures. A room is not marked `READY` until housekeeping, maintenance, and a retained-policy manager provide fresh, non-conflicting evidence for the same turnover generation.

## Included

- agree one property identifier, room roster, current turnover IDs, manager allowlist, and freshness windows;
- map buyer-approved de-identified housekeeping, maintenance, and manager-release evidence into the strict input contract;
- exercise clean, blocked, missing, stale, future, conflicting, unauthorized, and wrong-turn cases;
- deliver deterministic JSON historical receipts plus a current-replay acceptance sheet;
- deliver the policy/evidence schemas, retained-policy verifier, hostile regression suite, and receipt-retention procedure;
- conduct one findings and acceptance review.

## Buyer acceptance hypothesis

The pilot is accepted when the agreed frozen test set and buyer-approved de-identified evidence set each produce exactly one deterministic decision per in-scope turnover; every `READY` binds all three required evidence classes to the same turnover; every hold names its reason; reordered equivalent input is deterministic; tampered or attacker-resealed output fails against the separately retained receipt; caller-rewritten policy cannot acquire production authority; and current-use verification replays freshness at verifier-owned UTC rather than preserving historical `READY` state.

## Explicit exclusions

- PMS or guest-data production access;
- production credentials;
- writing room status into a PMS;
- dispatching housekeeping or maintenance personnel;
- guest communications, charges, refunds, or booking changes;
- payment capture or revenue recognition;
- production deployment or recurring managed service;
- any claim that this compiler authenticates a hotel system of record.

Any production integration, live-system access, expanded property scope, or recurring operation requires a separately written scope, authorization, and price.

## Payment boundary

This document is a commercial scope template, not evidence of buyer acceptance, authorization, payment, cash, or recognized revenue. Work should be connected to an explicit paid path, but no buyer or payment state may be invented. Payment-link creation and outreach custody are separate from this fulfillment carrier.
