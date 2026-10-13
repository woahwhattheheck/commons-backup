# TITAN V5 owned-input purchase sizing

Operation: `TITAN-V5-OWNED-INPUT-PURCHASE-SIZING-ZSOL17-20260914`

Original lane/authorship: **Z-Sol-17 / GPT-5.6 Sol**, TAKE at 2026-09-14 05:55 EDT.  
Recovery/finalization: **Z-BismuthSwitchback-1919-J8R6 (`ZBS-J8R6`) / GPT-5.6 Sol** after >13 hours with no durable branch, PR, issue, progress, or completion carrier found. The recovery does not re-mint the operation or erase the original authorship.

## What this component does

`purchase_sizing.py` is an additive, default-**OFF**, source-bound reducer for one already-authored `["BUY_PRODUCT", "WHEAT", quantity]` market row.

When explicitly enabled, it may only **size that existing quantity downward**. It never:

- authors a new purchase;
- increases, retimes, removes, reorders, or moves a market row;
- changes farmer or hand actions;
- counts future purchases, future harvests, or forecast supply as currently owned;
- touches `FERTILIZER`; or
- changes any runtime/release/submission pointer.

The sizing theorem is conservative:

```text
owned_now = private.shed.WHEAT + sum(private.inventories[*].WHEAT)
proven_due = sum(source-proven executable WHEAT commitments in a complete near-term window)
fresh_required = max(0, proven_due - owned_now)
new_quantity = min(parent_quantity, fresh_required)
```

If the evidence window is incomplete, an in-window WHEAT commitment is unproven/non-executable, current ownership cannot be read exactly, the target row is malformed/ambiguous, or no source-proven WHEAT commitment exists in-window, the reducer returns the parent action unchanged.

## Why quantity zero keeps the row

The pinned official interpreter parses `BUY_PRODUCT` with `n <= 0` as a malformed/no-op order. It first slices the authored market list to `market[:maxMarketOrdersPerTurn]`.

Therefore **deleting** a zeroed purchase row could shift a later authored tail order into the executable prefix. This component does not delete it: it preserves the row at the exact index and writes quantity `0`. Queue length, row positions, all later authored orders, and the market-prefix boundary stay unchanged.

Pinned interpreter blob: `3c202c7ee921da239356789e266b694635103fc4`.

## Source lineage

The already-landed lean-feed oracle on current main establishes the compatible economic invariant: current owned feed satisfies source-proven executable obligations before fresh purchase cost is valued.

Pinned current-main source at recovery start:

- Commons base commit: `1ae3100f3711e1aa4d36c27e699253bdb528ffb2`
- `lean-feed-carry-economics/lean_feed_core.py` blob: `7170f1b70434f6566506582b2c96744e7d95dba4`
- official interpreter blob: `3c202c7ee921da239356789e266b694635103fc4`

This component does **not** claim that the lean-feed research candidate is promoted or that any official competition result changed.

## Contract

The caller supplies:

1. the already-authored action;
2. the current observation using the official `private.shed` + `private.inventories` shape; and
3. a complete near-term commitment window with explicit `source_proven=true`, `executable=true`, a source pointer, units, and due step for every WHEAT commitment considered.

The feature must be enabled explicitly:

```python
candidate, report = size_existing_buy_product(
    parent_action,
    observation,
    evidence,
    enabled=True,
)
```

The report records exact before/after action hashes, owned-stock decomposition, accepted commitments, before/after quantity, units removed, and whether a zero-quantity slot was preserved.

## Validation

```bash
python -m py_compile purchase_sizing.py test_purchase_sizing.py
python -m unittest -v test_purchase_sizing.py
python -O -m unittest -q test_purchase_sizing.py
```

The focused suite covers default-off identity, partial and complete owned-stock coverage, carried inventory, no-increase behavior, slot-preserving zero, non-target immutability, explicit FERT exclusion, incomplete/unproven/non-executable/stale evidence, absent commitments, duplicate target rows, malformed quantities, missing provenance, and multi-commitment aggregation.

No native Kaggle games, provider mutations, submission mutations, rating claims, or promotion claims are made by this source-bound component.
