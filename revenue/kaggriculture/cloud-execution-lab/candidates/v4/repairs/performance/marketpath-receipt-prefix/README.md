# Exact MarketPath receipt-prefix reuse

Status: built and independently executed component for the single canonical
`main:candidates/v4`. Not installed in production and not a game-strength claim.

## What changes

The same method-pinned transformer targets `MarketPath._single` and `_joint`
in both `scheduler.py` (a483b24d) and the active `selected_sell_core.py`
(f23d3a8b). FrozenSelected uses the latter optimizer and the former for funding
stress. It does not replace either whole module, alter the objective or
candidate ordering, touch market queues, change configuration, or reset the
existing score-context/absorption cache.

Each MarketPath gets at most 64 receipt series, each at most 101 entries.
Single-stream series accumulate sequential **floats**, exactly like the legacy
receipt API. Paired series accumulate **integers**, exactly like the engine's
simultaneous quote loop. The equal-length shared part advances inventory by
two only when the quoted price exceeds one; an asymmetric tail advances by one.
Before/after alignment still invokes the unchanged single-stream interface.
At the price floor, cash is paid but inventory does not advance. No monotonicity
approximation, prefix-sum subtraction, price interpolation, or policy change is
introduced. Numeric inputs outside the bounded fast domain use the original
code, including its original exceptions. Quotes/market parameters are assumed
pure and fixed during a MarketPath evaluation, as in its existing quote cache.

The fast domain is strict integer inventory with absolute value <= 2**52 and
strict integer quantities 0..100. This keeps the legacy float inventory walk
exactly representable. A large customized-price test proves why the two cash
accumulators cannot be merged: the predecessor's 13-unit single receipt is
117093590311632912 while its integer paired receipt is 117093590311632922.
Both distinct values are deliberately preserved.

## Executed evidence

13 tests pass normally and under `python -O`. Each mode executes 16,362 single
and 17,280 joint equalities, 540 customized-curve joint comparisons, 216 complete
optimizer comparisons with identical capacity-callback order, and 2,592 calls
to the pinned official `_process_market` across both physical seats. Six
numerical mutants fail actual semantic assertions in each mode, not merely
source-integrity checks. Drift, duplicate methods/classes, partial postimages,
repeat application, unrelated peer-method preservation, CLI overwrite and
in-place-write rejection are covered.

The 12 fixed complete-optimizer workload has a measured local median speedup
of 1.426x normally and 1.422x optimized Python. A quantity sweep keeps small
lots near parity and gives about 1.5x for several 100-unit lots. These are
synthetic component workloads, not whole-agent or hosted performance. One
100-unit allocation sample increases traced peak memory by roughly 0.29 MB;
the bounded cache is a deliberate time/memory tradeoff. Exact samples, source
hashes, counts, mutation results and profile values are in `VALIDATION.json`.

## Reproduce without changing production

Use the complete existing runtime from artifact 10123395668 (run34400824037),
with its official engine fixture. The checker verifies six exact source blobs.
It does not claim that every file in this historical archive equals a current
release. No new Actions run was dispatched for this work.

```sh
python check_marketpath_receipt_prefix.py --runtime /path/to/runtime --report normal.json --benchmark -v
python -O check_marketpath_receipt_prefix.py --runtime /path/to/runtime --report optimized.json --benchmark -v
python check_marketpath_mutants.py --runtime /path/to/runtime --report mutants.json
python -O check_marketpath_mutants.py --runtime /path/to/runtime --report mutants-O.json
python profile_marketpath.py --runtime /path/to/runtime --output profile.json
```

Report paths must be new. The engine gate uses explicit initialized market
states, not Kaggle framework initialization; when the Kaggle package is absent,
only its unused seed-resolution import gets a fail-on-use shim. No gameplay
function is stubbed.

For a staged runtime copy, transform **both** source modules; the CLI refuses
to overwrite existing paths or edit its input in place:

```sh
python marketpath_receipt_prefix.py /path/to/runtime/scheduler.py /new/path/scheduler.py
python marketpath_receipt_prefix.py /path/to/runtime/selected_sell_core.py /new/path/selected_sell_core.py
```

## Remaining integration gate

The single modern V4 composer owns staging these method deltas alongside its
existing scheduler-prefix repairs. Other methods and module bytes are retained,
but the fully composed current package still needs its own callback, memory,
real-deadline and paired whole-game gates. Faster computation can change which
work completes before a deadline; numerical equality is not a proof of equal
wall-clock fallback behavior. This package neither authorizes a default flip
nor claims an economic improvement. Do not execute a legacy r04 materializer,
create a successor V4, or rebuild this mechanism in a second package.

Coordination owner: ASTRA-MEADOW, claim1789180222.658529.
