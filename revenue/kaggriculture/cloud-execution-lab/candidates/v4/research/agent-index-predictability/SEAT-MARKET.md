# MW2 engine result: public seat identity is not market commit priority

ASTRA-SEAT / Commons issue #12655. One destination:
`main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/agent-index-predictability/`.
This supplements the existing empirical `analyze_agent_index.py`; it does not
replace that reporter or create another V4 implementation. No gameplay key,
default, runtime, archive, legacy materializer or Kaggle state changes.

## Executed result

The exact pinned interpreter sets `observation.player = i` during initialization,
before executing an action. Both seats already know their index when choosing
an action. Predicting platform assignment is unnecessary for conditioning a policy
on that public value. Hosted assignment control and the requested 231-game index
distribution remain unverified here; the empirical reporter/data owner retains
them. Rival same-turn actions and the hidden episode seed are not agent inputs.

**Market commit order does not create a p0 price advantage.** Both players' unit
prices are quoted from the same inventory before either commit. Exchanging whole
farm/private/action arms produced zero result mismatches over **2,048 synthetic
market cases**: all six market operations, scarcity/surplus/floor regimes,
cash/capacity failures, malformed inert rows and raw caps 10/1/2/0/-1. The 0/-1
cases are explicit engine-clamp controls, not valid hosted-config claims. The
comparison checks the full public market and logically reoriented farms/private
stores. A deliberately wrong sequential re-quote implementation fails this oracle.

### Positive control: raw slot, not physical seat

Both logical sellers start with 50 WOOL, $3,000, public WOOL inventory 10,000 and
standard settings; unit actions are PASS. Cash increases from one market call:

| Raw market arrangement | Logical A | Logical B |
| --- | ---: | ---: |
| Both SELL at slot 0 | 4,036 | 4,036 |
| A SELL at 0; B `[]` then SELL at 1 | 7,655 | 314 |

Both rows are unchanged after physically swapping p0/p1. This is a synthetic
mechanism control, not a full-game edge or promotion estimate. Executable raw-slot
alignment and opponent action inference belong to the existing lockstep lane;
current rival actions cannot simply be read from the observation.

### Source argument and boundary

For ordinary two-player engine states with separate private stores and finite
numeric values, both quotes use the common pre-commit inventory. Each acceptance
check uses only own cash/stock/capacity and its already-computed quote. Successful
inventory changes are additive; the $1 SELL exception uses that quote. BUY_PRODUCT
does not reserve a stock-limited common pool. HIRE/BUY_LAND affect only the acting
farm/private state. Thus swapping complete player arms swaps their decisions and
updates, preserves shared inventory, and by induction preserves every remaining
quantity/row and the final price refresh. This is not a claim about arbitrary
malformed objects, alternate engines, or later world transitions.

**Full-episode seat symmetry is false.** EOD uses one RNG across farms in player
order. Identical fresh farms, standard settings, seed 0/day 0: p0 gets no weed;
p1 gets a weed at `[0, 3]`. This executed countercontrol prevents extending the
market result to whole games. Actual candidate validation must still use both
seats. The harness's known test seed is not proposed as an agent input.

## Reproduction

From repository root, with the standard library:

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
ENGINE=$(pwd)/$LAB/reference/engine
WORK=$LAB/candidates/v4/research/agent-index-predictability
python "$WORK/seat_market_probe.py" --engine-dir "$ENGINE" --cases 2048 --output /tmp/seat-receipt.json
cmp "$WORK/SEAT-MARKET-RECEIPT.json" /tmp/seat-receipt.json
TITAN_ENGINE_DIR="$ENGINE" python -m unittest discover -s "$WORK" -p test_seat_market_probe.py -v
TITAN_ENGINE_DIR="$ENGINE" python -O -m unittest discover -s "$WORK" -p test_seat_market_probe.py -v
```

Executed on Python **3.13.5**: **24/24 normal, 24/24 optimized**, `py_compile` pass;
normal and optimized 2,048-case receipts match byte-for-byte. Python 3.11+
compatibility is intended, not separately executed. No hosted-CI or evaluator
fidelity claim is made. No full games or game-bank records were consumed.

The loader pins all three input files, executes the full engine, and substitutes
only its external seed import with the unchanged AST-extracted resolver from
pinned utils. No Kaggle installation or global sys.modules mutation is needed.
The specification is consumed from the same verified immutable bytes. Invalid
source/counts produce no report, output uses atomic replacement, and pinned
inputs cannot be overwritten. This is an isolated engine-function harness, not
a hosted agent run.

Recovered existing Actions artifact **10285621024**; all three files independently
match current-main reference source:

| File | Git blob | Bytes |
| --- | --- | ---: |
| kaggriculture.py | `3c202c7ee921da239356789e266b694635103fc4` | 40,356 |
| kaggriculture.json | `b354d06b742fe48402513792253f1a5c29366b20` | 6,002 |
| utils.py | `91c8822ee6201ba4a5a8416c7dbe34f95dd61c87` | 8,634 |

Engine source ranges: initialization 244-275; quote/commit 544-628; unit commit
652-687; EOD 860-891; initialization return 894-902. Utility resolver: 199-231.
`SEAT-MARKET-RECEIPT.json` binds those sources, controls and deterministic result
stream. Its self-hash uses canonical JSON before adding `receipt_sha256`.
`SEAT-MARKET-MANIFEST.json` binds only this added engine-evidence set, not the
independently maintained empirical analyzer.
