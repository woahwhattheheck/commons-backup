# Ordered market queue comparison

`queue_delta.py` compares two complete market queues on the same supplied
post-unit state. It reports current-market own/rival cash, resource changes and
slot-level execution effects without selecting an action or invoking a controller.
The module uses Python's standard library and the caller's existing official
market mechanics. It does not distribute another engine or source pack.

## Callable

```python
from queue_delta import compare_queues

report = compare_queues(
    mechanics,
    step=observation["step"],
    seat=observation["player"],
    own_farm=post_unit_observation["farms"][observation["player"]],
    own_private=post_unit_observation["private"],
    market=post_unit_observation["market"],
    baseline_action=selected_action,
    proposed_action=proposal,
    scenarios=rival_scenarios,
    configuration=configuration,
)
```

All input state is **after the already-selected unit phase and before market**.
The two actions must retain identical farmer/hand fields. The function does not
apply them again. A different unit proposal requires its own post-unit state and
is outside this same-state comparison.

Each rival scenario is an explicit dictionary:

```python
{
    "id": "prior-flow-with-specified-stock",
    "provenance": "Caller hypothesis; not observed rival private inventory",
    "farm": supplied_rival_post_unit_farm,
    "private": supplied_rival_post_unit_private,
    "action": {"market": supplied_rival_orders},
}
```

Provide the whole relevant farm/private state, including actual workers, their
inventory entries, daily hire count, land, cash, seeds and shed quantities.
Unknown rival stock must remain a scenario assumption, not be passed off as
observed truth. The same scenario is applied independently to both own arms.
Inputs are copied; returned state does not alias caller objects.

`mechanics` supplies the unchanged official `_process_market` and `_parse_order`.
`load_market_engine(path)` loads their exact transitive definitions from an
existing `kaggriculture.py`, without importing game initialization or drawing
randomness. It preserves function bodies and exposes the actual file SHA-256.
The caller supplies trusted local source, not arbitrary uploaded code.

## Report contract

A `complete_conditional` report covers every supplied scenario. Each row has
`baseline`, `proposed` and `delta`. Both execution arms contain full resulting
farm/private/market state, resource views and a slot trace. Delta reports
`own_cash`, `rival_cash`, `relative_cash`, resource-change flags and paired slots.
An `inherited_execution_changed` flag means an unchanged own order had a different
cash/resource effect after the preceding queue changed. It is not limited to
order text or nominal purchase costs.

The function invokes the original paired market function once per original slot,
retaining shared precommit quotes, relative order positions, partial fills,
funding, storage, hires and land. Tests compare the resulting **entire** state to
one unchanged complete-market call. Empty/no-op slots are not repacked, and the
engine's configured order limit is applied before execution.

`bounds` is the min/max of the included scenario cash differences, **not** a
probability, expectation, guarantee over omitted scenarios, terminal-value score
or game result. Extra hands or land may have later value or costs; this component
does not price that continuation. It runs no future units, shops or daily reset.
The caller's admission, preservation and policy-selection logic stays separate.

Default limits are 32 scenarios, 128 configured order slots and 20,000 estimated
unit-work steps. An optional absolute `time.monotonic()` deadline is checked
between slots, not enforced by interrupting an engine call. Missing/inconsistent
state or exhausted bounds returns `unknown`, with no aggregate bounds or selected
action. Completed scenario rows may remain as diagnostics; they are not a partial
ranking. Limits are component work bounds, not a whole-agent timing guarantee.

## Source and reproduction

Validated against `Kaggle/kaggle-environments` commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`:

- `kaggle_environments/envs/kaggriculture/kaggriculture.py` SHA-256
  `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.
- Existing engine artifact `10005621438` was reused, ZIP SHA-256
  `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`.
- Engine license: Apache-2.0, retained in that cache's `LICENSE` and the existing
  `cloud-execution-lab/reference/engine/LICENSE`. No modified engine is added here.

The test cache contains the existing `kaggriculture.py`, `kaggriculture.json` and
framework `utils.py`. No download, install or new export job is attempted:

```sh
D=revenue/kaggriculture/cloud-market-queue-delta
python "$D/test_queue_delta.py" --engine-cache /path/to/existing/engine \
  --result /tmp/queue-validation.json
python "$D/queue_delta.py" --engine-source /path/to/existing/engine/kaggriculture.py \
  --input /path/to/case.json --output /tmp/queue-report.json
```

CLI input keys match the callable's keyword arguments, excluding `mechanics`.
Exit 0 means a complete conditional comparison; exit 2 means unknown. The output
records the actual engine file hash. `validation.json` records the executed
source/test hashes, counts and test duration.

24 focused tests pass, covering 146 comparison cases and 294 independent full
market reference calls. Coverage includes both positions, simultaneous buys,
rival receipt changes, SELL-funded purchases/hires, repeated land/hiring, animal
and seed storage, floors, custom market parameters, malformed no-ops, truncation,
nonmutation, CLI execution and partial-deadline handling. No scored game or seed
is consumed. This is component correspondence, not hosted CI or policy promotion.

## Consumer context

LOSS-DELTA's already-landed selected-seed proposal and its retained seed-to-HIRE
negative are separate work: PR9961, commit
`36ec529659f038725ce325a19c2079a2a5b898b7`,
`cloud-selected-seed-budget/test_selected_seed_budget.py`,
`EngineTests.test_freed_cash_can_enable_later_hire_negative_not_guaranteed_saving`.
This executor does not rebuild that demand adapter or repeat its fixture panel.
Our distinct sale-funded-HIRE case demonstrates the reusable slot attribution.

A seed-demand bound does not establish unchanged execution of later orders.
Likewise, retaining a rival scenario as possible/unknown does not certify our own
continuation feasible. Feed the complete queue reports into the existing consumer;
keep uncertain rival scenarios and future economic valuation explicit. No selected
policy, peer source path, held panel or original evidence is changed here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
