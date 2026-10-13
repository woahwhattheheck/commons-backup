# Commercial Cash-Realization Ledger

A buyer-neutral, standard-library-only evidence ledger for one question the revenue swarm must never blur: **what is commercial progress, and what is actually evidenced as received money?**

The ledger keeps these states separate:

`OPPORTUNITY → ACCEPTED → AWARDED → REQUESTED_OR_INVOICED → PAYMENT_PENDING → PARTIALLY_RECEIVED / RECEIVED → REVERSED → RECONCILED`

Any evidence/authority/chronology/amount conflict produces `HOLD`.

## Why this exists

An advertised bounty, accepted proposal, sponsor award, invoice/payment request, and provider “pending” notice are useful commercial facts. None is cash. Only a verified `PAYMENT_RECEIVED_EVIDENCE` event backed by `payment_provider_evidence` or `bank_record` can increase the ledger's received amount. Reversals reduce it. `RECONCILED` additionally requires an owner-approved reconciliation event matching the exact current net receipt evidence and occurring after the latest cash event.

This is intentionally distinct from the funded-work reward-amount gate: that gate can determine the current advertised/canonical reward amount; this ledger answers whether and how external receipt evidence realizes a separately declared commercial reference amount.

## Schema v2: exact event-bound evidence

Schema v1 is intentionally rejected. In v1, an evidence row named a source digest/reference and authority but did **not** commit to the event it allegedly proved. The same bank/provider row could therefore be reused across changed amounts, times, event IDs, event kinds, or claims and mint more than one cash fact.

Schema v2 closes that boundary:

- every evidence row contains `event_sha256`, the SHA-256 of the complete canonical event object;
- event binding covers event ID, exact claim digest, event kind, occurrence time, evidence ID, and amount when present;
- an evidence ID may be referenced by only one event;
- the same external source bytes (`sha256`) may not be cloned under multiple evidence IDs, regardless of caller `authority` or free-form reference;
- event mutation or claim transplant after binding fails closed before cash arithmetic;
- `event_sha256` is an integrity binding only. It does **not** authenticate a bank/provider, validate source bytes, or turn a caller-supplied authority label into independent provider truth.

Callers migrating v1 packets must re-derive each evidence binding from the exact event they intend the evidence to support. A legacy unbound packet cannot obtain current `RECEIVED`/`RECONCILED` state.

## Authority matrix

- opportunity: internal record / owner approval
- acceptance: counterparty or sponsor evidence
- award: sponsor evidence / public award
- request or invoice evidence: internal or counterparty evidence
- payment pending: sponsor or payment-provider evidence
- payment received / reversal: payment-provider evidence or bank record
- reconciliation: owner approval

A self-authored owner note **cannot mint received cash**.

## Input model

Each claim is PII-minimized and immutable: opaque claim/counterparty refs, kind, currency, exact integer minor-unit reference amount, creation time, source ref, and SHA-256. Every event binds the exact canonical claim digest so cross-claim transplantation fails closed. Every evidence record is referenced by exactly one event and binds that exact canonical event using `event_sha256`; evidence also carries independent status, authority, capture time, source reference, and source digest.

`reference_amount_minor` is owner-supplied commercial reference metadata. It is **not** a debt, invoice balance, collectible amount, accounting receivable, earned revenue, tax base, or cash assertion.

## CLI

```bash
python revenue/cash_realization_ledger/cash_realization_ledger.py compile \
  --input packet.json \
  --json-out ledger.json \
  --markdown-out ledger.md \
  --csv-out ledger.csv

python revenue/cash_realization_ledger/cash_realization_ledger.py verify \
  --input packet.json \
  --ledger ledger.json
```

`--fail-on-hold` exits `2` when any claim is held. Ordinary outputs are create-exclusive and final-component symlinks are refused.

## Invariants

- exact integer minor units; bool/float money rejected;
- claim reference amounts and monetary events stay strictly positive, except a
  reconciliation amount may be zero when the exact current net receipt evidence
  is zero after a full reversal;
- no implicit FX and no cross-currency grand total;
- exact evidence authority per event kind;
- every evidence row commits to exactly one canonical event generation;
- one evidence ID cannot authorize multiple events;
- duplicate external-source-byte aliases fail closed even if caller authority, free-form reference, or local evidence ID changes;
- pending/rejected evidence cannot advance a state;
- evidence capture cannot predate the represented event;
- event cannot predate the claim;
- cumulative receipt evidence above the declared reference amount holds;
- reversal cannot exceed receipt evidence accumulated up to that point;
- stale or amount-mismatched reconciliation holds;
- different amounts at the latest reconciliation timestamp hold as
  `CONFLICTING_RECONCILIATIONS`; event IDs do not establish chronology. A later
  unambiguous reconciliation can supersede the older conflicting assertions;
- zero reconciliation without receipt evidence still holds; it does not create a
  receipt or mark an unpaid claim as paid;
- duplicate semantic events hold instead of double-counting;
- exact deterministic recomputation verifies the JSON packet;
- no network/provider mutations or external actions.

## Authority ceiling

Evidence control only. No invoice issuance/send, buyer/sponsor contact, collections demand, contract/legal conclusion, debt validity or collectability decision, accounting/tax treatment, revenue recognition, bank/Stripe/payment-provider mutation, payment initiation/refund, or deployment/spend. `RECEIVED` and `RECONCILED` are evidence states under this local model—not GAAP/bookkeeping conclusions. A source digest or `bank_record` / `payment_provider_evidence` label is supplied evidence metadata, not independently authenticated provider truth.

## Tests

```bash
python -m py_compile revenue/cash_realization_ledger/cash_realization_ledger.py
python -m unittest discover -s revenue/cash_realization_ledger -p 'test_*.py' -v
python -O -m unittest discover -s revenue/cash_realization_ledger -p 'test_*.py' -v
```
