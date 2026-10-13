# Revenue Event Ledger From Receipts

This package projects one buyer × offer × purpose lifecycle from immutable Slack, Gmail, provider, and payment receipts. It is intentionally buyer-neutral and read-only: it does not contact anyone, mutate provider state, infer sentiment from silence, or promote an automated acknowledgement into a human event.

## Lifecycle

Evidence may advance only through explicit receipt-backed transitions:

`START → RESEARCHED → MUSE_SELECTED → PROVIDER_SENT → HUMAN_ROUTED/SCOPE_REQUEST → PROPOSAL_SENT → ACCEPTED → PAID`

After `PROVIDER_SENT`, explicit `DNR` or `BOUNCE` receipts produce terminal negative states. `AUTO_ACK` and `SUPPORT_TICKET` remain side-events. A missing predecessor never gets inferred; the projector keeps the last supported state and emits a diagnostic.

`PAID` has an additional hard gate: the receipt must be `PAYMENT_SETTLED`, sourced from `PAYMENT`, contain settlement ID / positive minor-unit amount / 3-letter currency, and have `verified: true`. Without that evidence, both `money_evidence` and `cash_claim_authorized` remain negative. This is settlement evidence, not an accounting-policy determination.

## Collision / stale-owner diagnostics

`MUSE_SELECTED` receipts carry seat and expiry evidence. Multiple distinct unexpired seats for the same exact buyer × offer × purpose key emit `COLLISION_MULTIPLE_ACTIVE_MUSE_SELECTIONS`; an expired selection with no valid provider send emits `STALE_OWNER_SELECTION`. Diagnostics never rewrite evidence-backed lifecycle state.

## Silence and machine replies

Silence is always emitted as `NEUTRAL_NOT_EVIDENCE`. `AUTO_ACK` and `SUPPORT_TICKET` are collected separately and never satisfy `HUMAN_ROUTED`, `SCOPE_REQUEST`, or `ACCEPTED`. Human event kinds require `human: true`.

## Validation

```bash
PYTHONPATH=. python -m unittest discover -s apps/revenue_event_ledger/tests -v
PYTHONPATH=. python -O -m unittest discover -s apps/revenue_event_ledger/tests -v
```

No dedicated active workflow is added because Commons currently uses its full 67/67 workflow-surface budget. The test battery is committed as reproducible evidence and remains subject to the repository's retained PR guards.
