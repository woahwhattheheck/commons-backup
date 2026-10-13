# TITAN V3 production → realization transaction gate

This candidate closes a specific score-facing gap in the current V3 architecture:
unit-action changes and market changes are authored by different hooks, so an
otherwise legal `PLANT`/`WATER` mutation can be action-causal but terminal-score
null when the inherited route never harvests, explicitly drops, and sells the
new output.

`production_realization.py` does **not** invent a crop plan or predict the
engine. It is the atomic commit boundary between a route constructor and an
exact official-engine evaluator. A sparse candidate route is returned only when
every declared scenario produces a complete receipt proving the whole economic
lifecycle and a strict terminal-score gain. Every decline returns the exact
parent route object.

## Admission contract

`admit_realized_patch(...)` requires all of the following:

- the sparse patch changes only steps in `[now, rejoin_step)`;
- the inherited action tape is byte-identical from `rejoin_step` through the
  terminal executable step;
- strict-JSON SHA-256 digests bind every receipt to the exact parent and
  candidate route slices;
- all scenarios use one pinned engine SHA and complete before the shared budget;
- unrelated control state rejoins and existing obligations are preserved;
- the candidate cash trough never becomes negative;
- at least one changed pre-rejoin action commits each realized lot;
- each lot preserves item identity and has causally ordered
  `commit → harvest → explicit DROP → positive-cash sale` evidence;
- harvested, explicitly dropped, and sold quantities match exactly; and
- candidate terminal score exceeds the parent by more than `minimum_gain` in
  every scenario.

A physical lifecycle alone is insufficient: a terminal tie is rejected. A
positive score delta alone is also insufficient: missing provenance, automatic
end-of-day deposit, partial sale, zero-cash/floor-price sale, or displaced parent
obligations all reject.

## Evaluator interface

The caller supplies:

```python
def evaluate(base_route, candidate_route, scenario_name, deadline):
    # Run the pinned official interpreter and return the receipt below.
    ...
```

The gate passes disposable deep copies into the evaluator, so simulator mutation
cannot corrupt the transaction routes. `deadline` is an absolute
`time.perf_counter()` value, or `None` when the caller explicitly disables the
budget.

Required receipt shape:

```python
{
    "complete": True,
    "scenario": "known_demand",
    "base_route_sha256": "...64 lowercase hex...",
    "candidate_route_sha256": "...64 lowercase hex...",
    "engine_sha256": "...64 lowercase hex...",
    "trace_sha256": "...64 lowercase hex...",
    "rejoin_control_base_sha256": "...64 lowercase hex...",
    "rejoin_control_candidate_sha256": "...same digest...",
    "existing_obligations_preserved": True,
    "base_terminal_score": 100.0,
    "candidate_terminal_score": 112.0,
    "candidate_minimum_cash": 5.0,
    "events": [
        {"kind": "commit", "step": 10, "lot": "tile:4,7:cycle:1",
         "item": "WHEAT", "quantity": 1},
        {"kind": "harvest", "step": 58, "lot": "tile:4,7:cycle:1",
         "item": "WHEAT", "quantity": 3},
        {"kind": "drop", "step": 58, "lot": "tile:4,7:cycle:1",
         "item": "WHEAT", "quantity": 3, "explicit": True},
        {"kind": "sale", "step": 59, "lot": "tile:4,7:cycle:1",
         "item": "WHEAT", "quantity": 3, "cash_delta": 12.0},
    ],
}
```

`rejoin_control_*` should digest only state that is not the declared lifecycle
payload: worker positions, hands/hires, private inventory, and pre-existing farm
obligations. The candidate may still carry its declared crop/animal state across
the action-tape rejoin until the inherited suffix realizes it.

## Integration point

Use the gate after a candidate producer has authored a complete sparse route and
before publishing that route to runtime selection:

```python
config = AdmissionConfig(
    now=observation["step"],
    terminal_step=configuration["episodeSteps"] - 2,
    rejoin_step=proposal["rejoin_step"],
    minimum_gain=0.0,
    seconds=0.15,
)
selected_route, report = admit_realized_patch(
    parent_route,
    proposal["patches"],
    config=config,
    scenarios=("known_demand", "matched_supply_pressure"),
    evaluate=official_engine_evaluator,
)
```

This is deliberately default-off and additive. It does not modify canonical
TITAN, does not overlap route-checkpoint regret, dual-chain holdback, E11/E20,
market-prefix transport, or the existing fourth-quadrant funded-payback route
constructor. The existing exact funded-payback simulator is a natural receipt
producer once its event trace is exposed in this schema.

## Validation

Run from this directory:

```bash
python -m unittest -v test_production_realization.py
```

Current local result: **34/34 tests pass**. The suite includes the observed
score-null `PLANT`/`WATER` class, weakest-scenario rejection, route/engine/trace
binding, partial realization, nonpositive sale cash, automatic deposit,
obligation and cash failures, malformed/NaN inputs, evaluator exceptions and
budget overruns, mutation isolation, and exact parent-object preservation.

No leaderboard-strength or release-selection claim is made by these unit tests.
The next acceptance step is an official-engine adapter plus hosted paired
matchups against the current V1 anchor and canonical V3 candidate.
