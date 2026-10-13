# Funded production-bundle admission

`funded_payback.py` is the ECON callback for a route producer that proposes a
complete paid-land production tail. It does not build a route, move a worker,
call an agent, choose a crop portfolio, or edit a live controller.

## Consumer interface

The direct evaluator remains available to any complete route producer:

```python
report = evaluate_bundle(
    observation,
    configuration,
    mechanics,
    base_route=controller.R[controller.cur],
    candidate_route=proposal["route"],
    bundle={
        "route_id": proposal["route_id"],
        "base_route_id": controller.cur,
        "target_quadrant": proposal["target_quadrant"],
        "rejoin_step": proposal["rejoin_step"],
        "required_tiles": proposal["tiles"],
        "minimum_planted_tiles": len(proposal["tiles"]),
    },
    minimum_gain=0,
    seconds=remaining_component_budget,
)
if report["complete"] and report["admitted"]:
    proposal.commit()
```

WIDEFIELD's landed sparse proposal interface is consumed without reconstructing
its planner:

```python
admit = FundedPaybackAdmission(seconds=0.35, max_proposals=3)
chosen = admit(mechanics, observation, configuration, controller.R, proposals)
diagnostics = admit.last_report
```

`FundedPaybackAdmission` materializes each supplied `variants[*].patches` tail,
requires every compatible authored route variant to pass, and returns the exact
proposal object expected by `FourthQuadrant`. Its proposal metadata is used only
for sparse-route materialization and bounded scan ordering. Funding, maturity,
yield, shed admission, sales and cash are recomputed with official mechanics.

The producer supplies complete authored base/candidate routes. The callback
requires the candidate to rejoin the exact base suffix, retain every existing
market order as an unchanged queue prefix, and add exactly one funded purchase
of the next locked quadrant. It executes both tails from the current own/public
observation with the supplied pinned mechanics. Every pre-existing purchase
that fills in the base must still fill in the candidate.

The target is admitted only when every proposed target tile is planted and
watered during the land-purchase day, then matures under the official crop
rules, is harvested, is explicitly returned to the shed, and is realized in
sales.
Private stock, existing-quadrant tiles, worker positions, and the authored
suffix must rejoin. The worst paired final-cash gain across every declared
market scenario must be strictly above `minimum_gain`.

`default_scenarios(...)` compares two source-prospective conditions:

- demand from shops already visible in the current observation plus the known
  town-center schedule, with no added rival flow;
- the same demand with a rival conditionally selling the candidate's scheduled
  quantities in the same slots.

Both routes see the same scenario. No future shop draw, environment seed,
replay row, opponent action, opponent private inventory, or future observation
enters the callback. Callers may supply other `MarketScenario` values only when
their complete conditional order queues are derived from current public inputs.

## Integration ownership

WIDEFIELD owns `cloud-widefield-lab/fourth_quadrant.py`, worker movement, spawn
semantics, route construction, and post-return commit/recovery. The callback
accepts or rejects that complete proposal; it must not be installed as a second
producer. T08 owns the one canonical `TitanAgent` lifecycle and package.

The callback is cooperative and fail-closed: invalid input, an incomplete
scenario vector, or elapsed component budget returns `admitted: false`. This is
not a replacement for the outer one-second action guard.

## Validation

The focused test drives the pinned official interpreter independently and
compares both seats' actual cash with the callback for the positive scenario.
The positive case deliberately supplies a one-tile bundle and a high configured
CARROT quote to make a small fixture pay back; it is engine-valid but not a
naturally reached game or a full fourth-quadrant strength claim. The direct
evaluator defaults to every tile in the target quadrant when `required_tiles`
is omitted; the WIDEFIELD adapter verifies every tile in its finite proposal.

Fourteen focused methods cover both seats, simultaneous matched supply, land and
seed funding after an existing queue prefix, later obligation starvation,
maturity, same-day water, explicit drop, realized sale, partial saturation,
route/worker rejoin, non-payback, incomplete compute, sparse proposal identity,
and rejection when any compatible route variant fails. Reproduce in the
existing cloud environment:

```sh
python3 -B revenue/kaggriculture/cloud-economic-stress/funded_payback/test_funded_payback.py \
  --engine-dir "$ENGINE_DIR" \
  --loader revenue/kaggriculture/cloud-execution-lab/reference/evaluator/loader.py \
  --report /tmp/funded-payback-results.json
```

This directory is Apache-2.0. The Kaggle engine and peer components retain
their own licenses and attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
