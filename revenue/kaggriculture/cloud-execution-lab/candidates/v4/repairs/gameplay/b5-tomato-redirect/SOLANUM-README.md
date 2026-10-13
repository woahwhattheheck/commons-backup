# B5 companion: use fertilizer certain to be discarded

SOLANUM-2863, claim `1789182863.639479`. One canonical `main:candidates/v4` component, in the same B5 family as FRUITPROOF's independent acceptance. This is **new experimental source**, not the unpublished historical `b5_tomato_redirect.py`. That donor and its effective gated configuration remain unrecovered. The legacy `r04_b5_tomato_fertilizer` switch is not repurposed or claimed repaired.

## Physical rule

`discarded_fertilizer_tomato.apply_discarded_fertilizer(observation, action, configuration=None, *, enabled=False)` returns `(action, report)`. Disabled or unsupported cases preserve exact action identity. Only a live worker's literal PASS on an already-watered, productive TOMATO can become FERTILIZE. Require carried fertilizer, default engine geometry/timing, actual hour 23 through step 695, next-day crop age 8..11, yield <=2, and coverage not already active.

A full shed and the absence of shed-removing live unit commands or executable raw-prefix SELL certify that the spent fertilizer would instead be discarded at that EOD. Other market rows are preserved. Engine cap `max(1, maxMarketOrdersPerTurn)` is respected without compacting empty slots; ignored SELL suffixes do not incorrectly veto the rule. Ghost actor rows are retained because even a ghost PLANT can affect atomic seed demand, but ghost PICKUP is not treated as a live shed transfer. Collocated destructive/service work vetoes a target; duplicate targets are serviced once. No observations or actions mutate.

The complete next transition has exactly one extra TOMATO per selected tile and extended fertilizer coverage, with otherwise equal world/environment/private state after neutralizing those two advertised tile fields and the returned command. This does **not** prove later cash: the extra crop still needs harvest, shed admission and sale, and can affect later planting. Reports describe proposals, never observed fills.

## Native binding, not a post-main wrapper

`compose_native.py` authenticates the exact native artifact's manifest and all 109 input runtime members, then creates a new scratch output. It rejects changed inputs, existing destinations and output inside the input. It never runs the old R04 materializer or writes production.

The real native Features/config path gets a strict, default-false `tomato_discard_salvage` key. `_finish_production` applies the optional rule **after** the last market guard and **before** final lifecycle receipts. Protected spatial/input/crop/terminal/capital plans veto it; deadline fallback never runs optional work. A changed unit action invalidates the old post-unit snapshot and consumer binding instead of inventing an observed fertilizer fill. Only after finalization is the selected fallback action rebound to the actual returned bytes. OFF config and unrelated runtime members remain unchanged.

This composer is bound to archived native source, not today's full combined stack. Later native/composer changes need an explicit source rebase and repeated gates. Do not transplant its whole runtime into a newer V4, stack a second post-main wrapper, or enable it on zero-opportunity evidence.

## Reproduce

Use the existing GitHub workflow artifact `10175943272`, extracted to an absolute directory with `final-pressure-runtime`. ZIP SHA256 is `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`. The scripts authenticate engine and runtime bytes without network fallback.

```sh
export TITAN_NATIVE_ROOT=/absolute/path/to/final-pressure-runtime
cd revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/b5-tomato-redirect
python -B test_discarded_fertilizer.py --report /tmp/b5-helper.json
python -O -B test_discarded_fertilizer.py --report /tmp/b5-helper-O.json
python -B test_native_binding.py --report /tmp/b5-native.json
python -O -B test_native_binding.py --report /tmp/b5-native-O.json
python -B run_semantic_mutants.py --report /tmp/b5-mutants.json
python -B compose_native.py "$TITAN_NATIVE_ROOT" /tmp/b5-off
python -B compose_native.py "$TITAN_NATIVE_ROOT" /tmp/b5-on --enabled
for seat in 0 1; do
  python -B native_census.py "$TITAN_NATIVE_ROOT" --seed 17 --seat "$seat" --report "/tmp/b5-base-$seat.json"
  python -B native_census.py /tmp/b5-off --seed 17 --seat "$seat" --report "/tmp/b5-off-$seat.json"
  python -B native_census.py /tmp/b5-on --seed 17 --seat "$seat" --report "/tmp/b5-on-$seat.json"
done
```

Use fresh scratch destinations. Each native census is a separate foreground process; comparisons must group the same seed/seat/opponent and compare both action and world/environment hashes. Timing fields naturally vary. The mutation runner itself executes normal and `-O` controls and every deliberate fault; import errors/skips do not count as rejected faults.

## Executed scope and disposition

Own tests: 18 helper + 10 native binding tests in EACH Python mode, zero failures/errors/skips. Helper suite executes 746 full interpreter calls/mode and 212 complete-world pairs, 180 activated. Twelve helper faults and six native binding faults are assertion-rejected in EACH mode, with zero test errors/skips. Native binding uses the actual factory/finalizer with explicitly controlled hook fixtures; those fixtures are not field games.

Constructed final-day harvest/drop/sale suffixes realize +84/+60/+1 cash in both seats at the three fixed tomato inventory levels; no-harvest continuation realizes zero. These are mechanism controls, not competitive wins.

Six actual native games (archived BASE, composed OFF, composed ON; seed 17, both seats) complete all 4,314 callbacks with zero fallbacks and per-seat identical entire action and world/environment traces. Each game has zero visible TOMATO callbacks and all 29 EOD sheds below full capacity. This is **NO_OPPORTUNITY_IS_NOT_A_KILL**, not strength or whole-stack promotion evidence.

FRUITPROOF's files in this same directory own independent engine acceptance; their initial receipt pins the earlier conservative helper `31cddc7`, not this ghost-row-aware successor `cc30bf4c`. ORCHARD owns the legal-from-initializer tomato-bearing fixture in `research/tomato-window`; its evidence remains separate. No peer tests or fixture gains are counted as this session's executions. Original donor custody, engaged current-native games, opponent diversity, replication and final shared-stack composition remain distinct open gates. Production/config defaults, submission archive and Kaggle are unchanged.
