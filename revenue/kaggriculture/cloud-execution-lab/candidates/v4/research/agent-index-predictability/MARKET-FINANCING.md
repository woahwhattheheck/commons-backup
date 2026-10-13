# Market financing: sale receipts are not terminal cash margin

ASTRA-MARKET-TEMPO. Additive evidence in the existing
`main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/agent-index-predictability/`.
The MW2 seat probe and empirical analyzer are untouched. No policy, new controller,
feature key, production default, archive, legacy materializer or Kaggle change.

## Executed counterexample on the actual current pressure component

At the final legal callback, step 718, both actors PASS. Each player has two MILK
in the shed, public MILK inventory is 10,000, own cash is 0 and rival cash is 682.
Parent own market is `[[], ["SELL", "MILK", 2]]`; the fixed rival market is
`[["SELL", "MILK", 2], ["BUY_LAND"]]`. Exact current pressure source `72616749`
moves our sale across the empty slot. The full pinned official interpreter returns:

| Outcome | Parent | Earlier own sale |
| --- | ---: | ---: |
| Own terminal cash | 310 | 316 |
| Rival terminal cash | 0 | 998 |
| Own minus rival | +310 | -682 |
| Rival land purchase | Executed | Unaffordable |

The same result was executed in both physical seats, with DONE statuses and
rewards equal to those bank totals. Our sale receipts rise 6 and rival sale
receipts fall 2: **sale-receipt margin improves 8 while terminal margin falls 992**.
The rival's skipped 1,000 land purchase explains the reversal. Cow, HIRE, partial
seed purchases and partial fertilizer purchases have analogous witnesses.

This does not refute the narrower sale-receipt argument in pressure compaction.
It refutes extending that argument to universal final cash or win/loss dominance.
These are synthetic microstates, not naturally observed games or an estimate of
how often a capable opponent buys unusable capital at the end. No recommendation
to disable the current feature follows from this evidence alone.

## Coverage and limits

The explicit, threshold-calibrated stress grid has 2,520 slots: seven sale-only
goods, three market inventories, three requested/available stock pairs, five
purchase families, four cash offsets, and both seats. 300 slots would require
negative initial cash and are explicitly excluded before execution, leaving 2,220
paired microstates. This is deliberately adversarial construction, not an unbiased
field panel, and its counts must not be presented as win rates or expected value.

Across those 2,220 pairs, 1,380 actions change; 168 have negative cash-margin delta
but **zero have negative sale-receipt-margin delta**. 108 create a terminal loss
from a parent win or tie. Worst cash-margin delta is -998. The report separates
positive 716, unchanged 1,336, and negative 168 cash cases; it retains all executed
negative results. All five purchase families have negative controls.

The 25-test suite passes normal and `python -O` on Python 3.13.5. It covers actual
full-interpreter rewards; both seats; affordable/unaffordable/threshold controls;
partial fills; floor paired-quote behavior; raw cap 1/2/10/12 and explicitly
non-hosted 0/-1 engine-clamp controls; dead rival raw suffixes; input custody;
source rejection; output protection; restoration after exceptions; and 24 exact
wrapped-versus-unwrapped interpreter poststate comparisons at EOD/terminal steps.
Six intentionally broken audit variants are each rejected in normal and optimized
child processes: sale receipts used as cash, reversed rival-spend sign, shared
input mutation, omitted purchase spending, accepted wrong source, leaked wrappers.

No full games, natural engagement census, replay corpus, performance benchmark,
hosted CI, hidden-rival predictor or promotion gate was executed here. The source
snapshot came from existing artifact 10123395668; only independently authenticated
component/reference files are used, not its older main.py or package archive.

## Reproduce from repository root

```sh
WORK=revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/agent-index-predictability
python "$WORK/market_financing_probe.py" --output /tmp/market-financing.json
python -O "$WORK/market_financing_probe.py" --output /tmp/market-financing-optimized.json
cmp /tmp/market-financing.json /tmp/market-financing-optimized.json
python -m unittest discover -s "$WORK" -p test_market_financing_probe.py -v
python -O -m unittest discover -s "$WORK" -p test_market_financing_probe.py -v
sha256sum /tmp/market-financing.json
```

The normal/optimized detailed JSON was byte-identical: 38,863 bytes, SHA256
`f677c4398673135e5abd68c7f0414ef5101d5e9f5a92fe46a899c49218457b26`.
The complete per-case result stream digest is
`e9ef10f7a0b8427fac75644a4129f7ea287563a037732e8f1d891e9eb0892d17`.
`FINANCING-VALIDATION.json` stores the compact durable result and source identities;
the command reconstructs the detailed report, including execution events and
witnesses. The full per-case stream is hashed, not stored as a replay corpus.

Both 25-test modes and the default-path CLI were rerun in a reconstructed canonical
repository layout using the exact source/test blobs read back from main. This
checks the documented import/path defaults, not unrelated whole-repository tests.

## Reuse without another policy or harness

`load_context(lab_path, pressure_path)` authenticates all seven source files before
execution and consumes the existing evaluator/loader from a captured temporary
fixture. It cannot fetch missing sources; wrong sources fail closed. The normal
and optimized runs use the same source pins. Outputs cannot overwrite those
inputs, Python source paths are rejected, and successful JSON output is atomic.

`compare_actions(ctx, state, env, seat, candidate_action)` accepts an incumbent
candidate's already-produced action and evaluates both actions from independent
copies of the same official state. Only cash-operation wrappers are installed;
the actual engine still owns unit actions, raw-prefix truncation, simultaneous
quotes, fills, capacity, town/EOD, and rewards. Wrappers are restored even on an
exception. Use its private engine in an isolated research process; it is not a
concurrent production instrumentation facility.

The returned ledger reconciles:

`delta cash margin = delta sale margin + delta rival spend - delta own spend + delta other cash margin`.

Rival same-turn actions/private stores are evaluation inputs only. They must never
be fed into an observation-only policy or presented as inferred public data.
LOT-MERGE, MARKET-SEQUENCE, pressure performance and LOCKSTEP retain their own
implementations; this probe supplies shared adversarial evidence, not another
market controller. Preserve both actual purchase fills and terminal rewards in
those gates rather than replacing them with hypothetical sales revenue.

Source commit: `a0eabedff4ce916d37f4cd64371d6fd49627c8e4`.
Test commit: `b236c4b78bc864c80a114758c88061af3bdf8f34`.
Source blob: `c10aa2d5e0a204a4d52a9fe5c0dd4d9418fa4880`.
Test blob: `bf247699d484faeb08b328e1303f4a082948d36f`.
