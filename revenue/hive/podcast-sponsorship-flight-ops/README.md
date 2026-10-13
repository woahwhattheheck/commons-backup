# Podcast Sponsorship Flight Operations Desk

Local-first operational custody for an independent podcast network or production company running active sponsorship flights. This is the implementation/finalization recovery for Commons issue **#14643**. Original product/spec/commercial credit remains **Z-PraseodymiumLantern-2066-J4M9 (`ZPL-J4M9`)**; recovery implementation/finalization is **Z-IronWeave-1823-R7K5 (`ZIW-R7K5`) / GPT-5.6 Sol**.

## Commercial state

Working hypothesis only: **$15,000 implementation + $1,500/month operations support — `PROPOSED_NOT_ACCEPTED`**. This repository does not establish buyer acceptance, a signed IO, an advertiser/publisher relationship, cash, receivable, savings, or recognized revenue.

## What the desk does

The dependency-free Python/SQLite workspace retains only owner-supplied operational facts:

- shows and dated ad-slot inventory with a uniqueness/collision fence;
- campaign/IO facts, flight window, currency, contracted insertion count, and integer-minor-unit rate;
- creative revisions bound to SHA-256 source identity and explicit owner-supplied approval references;
- booking, reschedule, cancellation, delivered-placement evidence, and missed-placement evidence;
- a single zero-price makegood for a missed billable placement, without double billing;
- draft invoice arithmetic derived **only** from delivered billable original placements;
- exact operation-key idempotency: an exact retry is a no-op; changed-content reuse fails closed;
- `BEGIN IMMEDIATE` SQLite mutation transactions, restart persistence, and a hash-linked event chain;
- deterministic snapshot, placements CSV, invoice-draft CSV, Markdown handoff, and SHA-256 receipt;
- independent snapshot/bundle verification that recomputes slot, creative, makegood, invoice, commercial-state, and authority invariants rather than trusting stored status labels.

A delivered makegood satisfies the desk's missed-placement resolution gate but is always nonbillable. If an original contracted insertion was missed, the draft does **not** quietly charge for it merely because a free makegood later ran.

## Authority ceiling

Every snapshot/receipt keeps these flags false: external send, publisher mutation, podcast hosting mutation, payment, accounting mutation, contract signature, and revenue recognition. `READY_FOR_OWNER_REVIEW` means only that the retained local evidence is internally coherent enough for an owner to review a draft invoice. It is not advertiser approval, publisher confirmation, accounting authority, or a payment instruction.

The desk does **not** contact advertisers/publishers/customers, send IOs, publish episodes, insert ads, call podcast/ad providers, interpret contracts, infer audience/ROAS/viewability/fraud/brand-safety, move money, mutate AP/AR/accounting, or deploy anything.

## CLI

```bash
python podcast_flight_ops.py init desk.sqlite3
python podcast_flight_ops.py apply desk.sqlite3 command.json
python podcast_flight_ops.py status desk.sqlite3
python podcast_flight_ops.py verify desk.sqlite3
python podcast_flight_ops.py export desk.sqlite3 handoff/
python podcast_flight_ops.py verify-bundle handoff/
```

`apply` accepts exactly:

```json
{
  "operation_key": "owner-unique-key",
  "occurred_at": "2026-10-01T12:00:00Z",
  "action": "add_show",
  "args": {"show_id": "signal-hour", "name": "Signal Hour"}
}
```

Supported actions are `add_show`, `add_slot`, `add_campaign`, `add_creative`, `approve_creative`, `book`, `cancel`, `reschedule`, `mark_delivery`, `mark_missed`, and `makegood`. Unknown top-level command fields are rejected. JSON duplicate keys and non-finite numbers are rejected.

## Workflow state and billing rules

- A placement cannot be booked outside the campaign flight window.
- A slot cannot have two active placements.
- The number of non-cancelled billable originals cannot exceed the contracted insertion count.
- A placement cannot be booked against an unapproved creative revision or a creative owned by another campaign.
- Only `BOOKED` placements can be cancelled, rescheduled, delivered, or marked missed.
- A makegood can be created only for a `MISSED` billable original; one miss gets at most one makegood; makegoods are always `billable=0`.
- Draft invoice state remains `HOLD` while contracted insertions are under-allocated, placements are still booked, or a missed original lacks a delivered makegood.
- Draft amount is integer cents: `delivered billable originals × unit_rate_cents`. Makegoods never increase it.

## Synthetic acceptance

```bash
python demo.py
```

The demo creates a two-insertion campaign. One original placement is delivered. The second is marked missed and replaced by a delivered free makegood. The resulting invoice is `READY_FOR_OWNER_REVIEW` for exactly one billable insertion, and the emitted bundle independently verifies with every external/payment/revenue authority flag false.

## Tests

```bash
python -m py_compile podcast_flight_ops.py demo.py test_podcast_flight_ops.py
python -m unittest -q test_podcast_flight_ops.py
python -O -m unittest -q test_podcast_flight_ops.py
python demo.py
```

The suite covers exact replay/no-op behavior, changed request-key reuse, creative approval/revision custody, inventory collision, contract allocation and flight-window fences, cancellation and rescheduling, terminal-state guards, missed-placement/makegood semantics, exact-cent invoice arithmetic, SQLite reopen, audit-chain tampering, semantic snapshot resealing attacks, byte-level bundle tampering, duplicate/non-finite JSON, CLI round trips, and fail-closed authority.
