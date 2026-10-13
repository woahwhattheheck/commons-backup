# Revenue experiment allocator v1

This module turns retained aggregate sales/outreach outcomes into a bounded **segment-level experiment plan**. It is a planning product, not an outbound sender.

## Purpose

The allocator answers a narrow question: given several offer/audience/route segments and retained aggregate outcomes, where should the next bounded batch of experiments be *considered*?

It deliberately does **not** choose recipients. Every allocated slot stops at:

`RECIPIENT_CENSUS_THEN_MUSE_ARBITRATION`

That means a downstream worker must still do a fresh recipient-level duplicate/DNR/ownership census and obtain fresh Muse single-writer arbitration before any email, form, DM, or portal message. Historical Muse evidence never becomes reusable send authority.

## Input contract

Each segment binds one evidence reference + SHA-256 and reports:

- available pre-deduped candidates;
- attempts -> delivered -> human replies -> positive replies -> proposals -> accepted -> paid;
- retained cash cents;
- historical DNR/collision counts;
- whether the current segment census is complete;
- whether an outbound route is available;
- whether a collision is unresolved.

A commercial segment is identified by the canonicalized tuple `offer_id × route_kind × audience_label`, not by caller-chosen `segment_id` alone. `offer_id` and `audience_label` are NFKC-normalized, whitespace-collapsed, and case-folded for the uniqueness fence; Unicode control/format characters are rejected at that identity boundary. Two rows therefore cannot alias the same commercial segment under distinct IDs or distinct evidence bindings to multiply the hard share cap.

The funnel counts must be monotone. Cash cannot exist without a retained paid signal, and a retained paid signal must carry positive retained cash.

The truth boundary is:

`AGGREGATED_RETAINED_OUTCOMES_NOT_PROVIDER_AUTHENTICATED`

Neither `paid` nor `retained_cash_cents` is upgraded to provider-authenticated cash. They are retained planning signals only.

## Allocation policy

A segment is held when evidence is stale, the current census is incomplete, an unresolved collision exists, the route is unavailable, or the segment has no remaining candidates.

Eligible segments are ranked deterministically by:

1. retained maturity (paid -> accepted -> proposal -> positive reply -> human reply -> delivered);
2. retained cash per attempt;
3. retained paid rate;
4. retained positive-reply rate;
5. lower historical DNR rate;
6. lower historical collision rate;
7. stable segment id tie-break.

There is intentionally **no headline ticket-value input**. The allocator uses observed retained outcomes instead of speculative deal size.

Two controls prevent naive winner-take-all spray:

- `max_segment_share_bps` caps any one semantic segment's share of the requested batch;
- `exploration_slots` reserves bounded capacity for strong collision-clean segments that have not yet produced a retained paid outcome.

Allocation is round-robin within the deterministic ranking, so the share cap is respected even when the requested batch is larger than available capacity.

## Authority ceiling

The output hard-codes all of these false:

- external send
- recipient selection
- Muse selection
- provider mutation
- contact creation
- payment movement
- receivable establishment
- accounting assertion
- revenue recognition

An order contains `recipient_identifiers: null` and `authority: PLANNING_ONLY_NOT_SEND_AUTHORITY`.

## CLI

Compile once, creating the output exclusively:

```bash
python -m revenue.revenue_experiment_allocator compile input.json bundle.json
```

Verify by deterministic recompilation:

```bash
python -m revenue.revenue_experiment_allocator verify bundle.json
```

Input loading is strict: bounded retained regular file, no symlink following when supported, descriptor-bound size/inode checks, duplicate JSON-key rejection, no floats/non-finite values, and bounded integers. Output uses create-exclusive publication.

## Tests

The root `test_revenue_experiment_allocator.py` and `test_revenue_experiment_allocator_strict_share.py` cover normal and hostile semantics including:

- ranking without headline ticket value;
- hard semantic-segment concentration cap, including non-divisible batch/share arithmetic;
- duplicate-ID aliases with distinct evidence cannot multiply capacity;
- NFKC/case/spacing aliases and Unicode format-character aliases are rejected;
- genuinely distinct route segments remain independently allocatable;
- exploration reservation;
- stale evidence / incomplete census / unresolved collision / route holds;
- exact monotone funnel and cash invariants;
- duplicate source binding rejection;
- bool-vs-int type strictness;
- bundle tamper rejection;
- planning-only order authority;
- paid signals remaining non-provider-authenticated.

Run:

```bash
python -m unittest -q test_revenue_experiment_allocator.py test_revenue_experiment_allocator_strict_share.py
python -O -m unittest -q test_revenue_experiment_allocator.py test_revenue_experiment_allocator_strict_share.py
python -m py_compile revenue/revenue_experiment_allocator/engine.py test_revenue_experiment_allocator.py test_revenue_experiment_allocator_strict_share.py
```
