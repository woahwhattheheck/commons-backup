# C5 public-WHEAT rider: current-runtime composition

Status: **current-ABI component tested, default OFF, not production promoted**.
Canonical home: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/c5-current-runtime`.
This is the existing `r04_c5_wheat_demand` mechanism, not a second trading policy.

## What was built

`compose_current_runtime.py` authenticates the exact modern runtime and existing
C5 donor before producing a two-file component in a NEW scratch directory. It
never executes a legacy materializer, imports the input runtime, edits the
production root, replaces the entrypoint, or emits a release archive. The donor
algorithm is copied unchanged; the modern `Features` key is literal `False`.
Explicit ON currently admits only nonterminal frozen SELL and requires an exact
boolean. OFF retains the existing consumer choices and imports no C5 donor.

C5's public inventory residual proves a lower bound on **gross rival WHEAT
buys**, not hidden net demand. A qualifying transition may move one already
written WHEAT SELL to a later raw market slot. The original helper retains its
floor-price, raw-prefix, funding, tuple-row, malformed-evidence, and quantity
rules. This port does not introduce buys, workers, land, or new sale quantities.

## Lifecycle integration

The actual modern runtime finalizes completed and selected-fallback actions
outside its main deadline timer, within the existing reserved finalizer window.
C5 construction/import runs inside `_initialize` under that timer; preview,
return binding, and commit run in the reserved finalizer window. This work does
**not** certify the real deadline backend or hosted timing budget.

The source placement is final feed-stock guard -> final early-capital guard ->
C5 preview -> quadrant/spatial/history finish -> C5 commit -> timing receipt ->
return. Therefore late buys cannot disappear from the next public residual, and
final observers receive the proposed sale rows rather than the pre-C5 rows.

Each TitanAgent owns its own `WheatDemandRider`. The module-global `RIDER` is not
used. A preview operates on a clone; finalizer failure leaves the committed
record unchanged. A deep-copied, recursively type-exact returned-action binding
must still match after finalizers before publishing the clone. Later row drift,
including `True` versus `1`, invalidates the latch. Prelude exhaustion clears
transition evidence without invoking a producer or a post-controller finalizer.
Selected-action fallback is observed but never relocated. Upstream normalization
of a string/float/bool clock cannot authorize C5 evidence.

## Exact source custody

Inputs were read from main commit `013af686a11f0da8c6e56e63e7b066b7f112d31f`
and independently materialized/hash-verified before execution:

* `titan_runtime.py`: 33,885 bytes; Git blob
  `b952c9c228ecbde592bf3d2df01638677abb0d24`.
* Existing `candidates/v4/donor/overlay/r04_c5_wheat_demand.py`: 12,800 bytes;
  Git blob `d5ea1757975099409a00a32e9c7eb6d40bf51926`.
* Composed runtime: Git blob
  `79027f03c6d46ad3cc7b30f21df7ba98d6cb9ff3`.

The exact-input composer deliberately rejects a newer runtime. It is not a
license to overwrite peer ports with this complete postimage. The single V4
composer must combine compatible semantic edits, then rerun current-head gates.

## Reproduce

From a checkout containing those exact input blobs:

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
P="$LAB/candidates/v4/repairs/gameplay/c5-current-runtime"
D="$LAB/candidates/v4/donor/overlay/r04_c5_wheat_demand.py"
python "$P/check_current_runtime.py" --runtime "$LAB/titan_runtime.py" --donor "$D" --mutations
python -O "$P/check_current_runtime.py" --runtime "$LAB/titan_runtime.py" --donor "$D" --mutations
python "$P/compose_current_runtime.py" --runtime "$LAB/titan_runtime.py" --donor "$D" --out /tmp/titan-c5-component
```

The output directory must not exist. Wrong/missing inputs or an existing output
are errors, never skips or automatic in-place updates. The two-file scratch is
NOT a runnable release package; its other runtime collaborators are intentionally
not copied. No current config or entrypoint is modified by these commands.

## Executed evidence and limits

`normal.json` and `optimized.json` record **26/26 tests**, no skips, **477 actual
TitanAgent.act calls** and **192 constructed transition cells per mode**.
The tests compile the complete original and composed runtime classes and the
complete unchanged donor. Actual act, initialization, selected transforms,
checkpoint handling, fallback branches, and finalizer methods run. Producer,
SELL, route, market-guard and timer collaborators are controlled doubles; they
are explicitly NOT official interpreter/game/economic results.

Five deliberately broken ports are rejected by assertions in EACH mode:
no preview clone (1 failure), relocating fallback (74 failures), no return binding
(2 failures), no prelude reset (1 failure), and preview before final guards
(2 failures). Additional checks cover strict/frozen OFF defaults, no OFF donor
load, loader inside the timer, both seats and multiple agents, final observer
rows, late funding, raw tails/caps, own-buy subtraction, town consumption,
malformed clocks/public data, cancellation at producer/transform/timer exit,
finalizer failure, repeated/gapped/rewound callbacks, input nonmutation, and
create-only deterministic composition.

Not run: official-engine or full games for this port; real SIGALRM/trace deadline
backend; hosted Python 3.11; full config/entrypoint/release package construction;
paired field or live economics; current-head composition with other recovered
ports. Before ON, bind the one authoritative SELL owner and preserve all later
raw-slot/funding semantics, then require current-head package and economic gates.
There was no production/default/archive/workflow/Actions/Kaggle mutation.
