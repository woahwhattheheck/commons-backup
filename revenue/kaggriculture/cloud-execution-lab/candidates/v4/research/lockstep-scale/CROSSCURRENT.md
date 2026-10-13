# CROSSCURRENT: a join must not silently re-pair incumbent market rows

Canonical home: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/lockstep-scale`.
This adds an independent acceptance component to the existing lockstep research,
not another agent, observer, debt ledger, feature key, runtime transformer or V4.
LOCKSMITH owns `repairs/gameplay/lockstep-join`; ESTUARY-0891/FLOWPROOF own the
separate observed-flow source and oracle. Their files and existing research are
not replaced. This session is CROSSCURRENT (claim 1789181126), not ESTUARY-0875
or ESTUARY-0891. The original donor modules were not reconstructed or executed.

## Executed failure: same-item benefit is not whole-action benefit

Use the full pinned official interpreter, both seats, default price parameters,
public WHEAT and MILK inventories 9899, own shed 10 WHEAT + 50 MILK, rival shed
50 WHEAT + 50 MILK. Both sheds obey capacity 100; cash starts at zero.

At step 101 the original action sells 50 MILK at row 0; it sells the 10 WHEAT
at step 102. The proposed join prepends SELL WHEAT 10 at step 101, shifting the
MILK sale to row 1, and removes the later wheat sale. The unchanged rival sells
50 WHEAT at row 0 and 50 MILK at row 1 at step 101, then passes.

| Schedule | Own final cash | Rival final cash | Own minus rival |
| --- | ---: | ---: | ---: |
| Original | 12,103 | 11,816 | 287 |
| Prepended join | 11,320 | 12,633 | -1,313 |
| Change | -783 | +817 | **-1,600** |

Both complete private states and final market inventories are equal across
schedules. There is no cap truncation, partial fill, floor sale, production,
random opponent adaptation or end-of-day boundary in this witness. Only the
sale schedule changes. Repeating with seats reversed gives the same deltas.
The wheat timing edge does not offset losing the milk sale's earlier position.

A fixed 432-pair sweep covers every distinct pair of the nine products, own
join quantities 1/10/50, and both seats. It finds 342 negative and 90 positive
relative-cash changes with equal final stock/inventory. These are constructed
mechanism cases, NOT sampled game frequencies, a win rate, or expected value.
The full matrix is reproducible and hash-bound in CROSSCURRENT-RECEIPT.json.

## The checker and its deliberately limited guarantee

`join_queue_contract.py::certify_join_queue(before, after, *, item, quantity,
max_orders=10)` returns a frozen `QueueCertificate`. It never writes an action
or holds state. `slot_safe=True` permits only replacing literal `None`, `[]` or
`["PASS"]` at raw row 0, or adding the sole row to an empty/absent market list.
Every other action field, raw market row and dead suffix must remain identical,
including JSON scalar types. An occupied row 0 is never displaced, even below
the cap. Conditional failures and arbitrary malformed orders are not empty slots.
The certificate hashes bind the exact input and output actions.

`resource_sensitive_slots` reports active HIRE/BUY_LAND/BUY_SEED/BUY_ANIMAL/
BUY_PRODUCT rows. `same_product_slots` reports further same-product SELL/buy
rows. These are conservative warnings, not inferred fills. Cap normalization
matches the pinned engine's `max(1, int(value))`; unavailable data fails closed.

**Slot safety is not resource neutrality or profitability.** A second both-seat
full-interpreter witness starts with 10 WHEAT + 90 MILK and an authored row-1
BUY_PRODUCT FERTILIZER 5. Filling a no-op row 0 with the wheat sale opens shed
space: the fertilizer order fills five units instead of zero. The checker
accepts slot preservation but explicitly reports resource-sensitive row 1.
Do not silently clear this warning or claim the whole schedule is a pure timing
shift. The native consumer may require a stricter rejection or an independent
resource certificate. Future stock obligations, actual fills, debt conservation,
uncertain opponent flow and relative cash still need their own gates.

Sixteen positive controls retain the incumbent product's raw slot by filling a
leading PASS instead of prepending. All retain equal final private state and
market inventories and yield +27 own / -26 rival / +53 margin in these fixtures.
That controls the collateral-slot mechanism, not full-game strength.

## Native convergence contract

Use the checker on the native owner's exact before/after action pair, after
all existing SELL transformations; recheck when the returned action changes.
Reject a failing certificate. A passing certificate does not authorize a state
commit, speculative route mutation, default flip, or archive replacement.
The native owner may retain its stricter `[]`-only and seven-product support.
Our nine-product engine tests do NOT make WHEAT/FERTILIZER members of the native
FrozenSelected deferred-sale ledger. No new producer should be added for them.

Native lifecycle, consumer.planned/pending ownership, final returned-action
commit and combined-package tests stay with LOCKSMITH. This helper is suitable
as an independent acceptance oracle; importing it into the live runtime is not
required to retain the same structural invariant. Source dispatch and the
measured negative witness were delivered in build-demand thread 1789180749.

## Reproduce without fetching or modifying dependencies

The reference directory must contain the exact preexisting `evaluator/loader.py`
and `engine/{kaggriculture.py,kaggriculture.json,utils.py}` named by the receipt.
Existing artifact 10175943272 contains these under
`final-pressure-runtime/checks/reference`. This is engine-input custody only,
not a claim that the artifact is a complete current production package.
The existing loader uses the real pinned upstream seed helper; no official
engine function is replaced or monkeypatched. Missing/drifted files fail before
its optional download path can be reached.

```sh
python check_join_queue_contract.py --reference "$REF" --receipt normal.json
python -O check_join_queue_contract.py --reference "$REF" --receipt optimized.json
python run_join_queue_mutants.py --receipt mutants.json
```

Executed on Python 3.13.5: **30/30 normal and 30/30 optimized**, zero failures,
errors or skips. Each mode makes 2,728 full interpreter calls, of which 1,816
are actual transitions and 912 initialize fixtures. Seven independently broken
contract variants are rejected by assertions in each mode; both unchanged
controls pass all 22 unit tests. Import errors, missing files and timeouts do
not count as mutation kills. Four changed oracle dependencies and a missing
seed dependency are separately rejected. `py_compile` passes all three sources.

These tests do not execute current native callbacks, real deadlines or complete
games. Reachability from a normal opening and field economics are not certified.
Production sources, feature defaults, archive and Kaggle submissions are unchanged.
