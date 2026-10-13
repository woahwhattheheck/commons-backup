# FLOWPROOF: independent public-flow acceptance for the single V4

Home: `main:candidates/v4/research/lockstep-scale`. This is an additive corpus and acceptance gate, not a second observer, bounds helper, join controller, feature key, or V4 tree. ESTUARY-0891 owns `effective_flow_bounds.py`; LOCKSMITH owns native observer/ledger integration. CROSSCURRENT and ESTUARY-ROW own collateral/timing economics. No production source, configuration, submission archive, or Kaggle submission is changed here.

## Executed finding

In both seats, the full official interpreter completes this transition: step 1, own cash 0, empty shed, returned `BUY_PRODUCT WHEAT 200`, rival PASS. Inventory remains 10000; actual own purchase and opponent inventory-changing flow are both zero. The displayed donor requested-quantity point formula returns **+200 opponent WHEAT**, above its 150 dump threshold. This is a reconstruction of the displayed formula, **not execution of unauthenticated donor bytes**.

Exact ESTUARY helper blob `e24dd03a88a71ba4cf6f8d5da1082b89490b5a94` returns WHEAT `[0,200]` and no confirmed positive flow. It is consumed unchanged, not copied into this delivery. Another executed control shows SELL WHEAT 200 with only three own units and a real rival sale of 20 yields donor point -177 while actual rival flow is +20. Floor sales can change cash/shed without increasing market inventory. The early hypothesis that town consumption clips at zero was rejected: this engine permits negative market inventory.

## Independent coverage and trust boundary

The corpus has 22 named worlds plus 96 fixed-seed mixed worlds, each in both seats: **236 transitions / 472 full interpreter calls per corpus build**. One call audits successful product commits and town deltas; its complete state and environment must exactly equal a second pristine uninstrumented interpreter call. All game function bodies remain unchanged. The only import adjustment replaces the unused external seed import with a raising guard; fixtures already have complete initialized state and a deterministic environment seed. All three upstream file pins are authenticated before compilation.

Cases cover empty and invalid raw rows, caps including normalization of zero to one, unsupported product buys, zero cash, full shed, partial purchases, short sells, numeric quantity forms, both-seat precommit floor crossings, rival floor-lifting purchases, negative inventories, duplicated town shops, EOD shop chronology, EOD carry deposits, pre-market unit DROP, and non-product cash competition.

`check_flow_bound_corpus.py` strips observations down to public seat/step, inventory and town, then passes only those fields, the exact own returned action and configuration. No prices, own/rival private state, rival action, audit trace or environment seed reaches the helper. It checks all nine products, repeated and reverse-order calls, input immutability and lower-bound-only signal selection. Retrospective net inventory flow is NOT a prediction of a future dump or a proof of profit.

Executed against e24dd03a in normal and optimized Python: 2,124 product containments per mode; 1,948 singleton intervals; 22 certified signals counted across thresholds 1/50/150; zero false-positive signals or input mutations. The gate rejects a vacuous all-wide/all-unknown answer, so containment alone cannot produce a green result.

## Reproduce

From this directory in a canonical checkout:

```sh
ENGINE=../../../../reference/engine
export FLOW_ENGINE_DIR="$ENGINE"
export FLOW_BOUNDS_HELPER="$PWD/effective_flow_bounds.py"
python -m unittest -v test_flow_engine_corpus test_flow_bound_corpus
python -O -m unittest -v test_flow_engine_corpus test_flow_bound_corpus
python flow_engine_corpus.py --engine "$ENGINE" --output /tmp/flowproof-corpus.jsonl
python check_flow_bound_corpus.py --engine "$ENGINE" \
  --helper "$FLOW_BOUNDS_HELPER" --output /tmp/flowproof-acceptance.json
python run_flow_corpus_mutants.py --engine "$ENGINE" --output /tmp/flowproof-mutants.json
```

Outputs must be new paths; existing files are never overwritten. For an extracted package, point ENGINE to its `checks/reference/engine` and supply the exact helper source. Dedicated acceptance fails on absent/wrong source. General unittest discovery explicitly skips the peer-helper class only if the optional adjacent source has not landed AND no explicit helper path was provided. An explicit missing source or any hash drift fails; neither is silently accepted. The recorded runs supplied the exact helper and executed all **27 tests with zero skips** in each mode.

Seven broken oracle variants are rejected under both modes: missing dependency pin, compacted raw slots, physical/admitted-flow confusion, all commits charged to seat zero, next-step consumption, erased town truth and leaked rival-private input. Eight additional bad helper contracts are rejected by the acceptance tests: upper-as-exact, fabricated zero, vacuous width, noninteger endpoints, missing product, input mutation, all unknown and upper-bound signaling. Mutation results are controls on this verifier, not extra game outcomes.

## Limits and integration disposition

This is constructed transition-level soundness evidence, not a full episode, real-opponent gauntlet, economic edge, natural activation census or production deadline benchmark. The helper's wide own-fill bounds can miss real flows; no stronger identification is claimed. Native action custody, same-episode binding, sale-plan provenance/debt handling, finalizer timing and future-dump economics remain their owners' separate gates. Keep the feature's activation decision separate from this acceptance receipt.
