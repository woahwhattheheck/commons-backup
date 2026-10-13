# Optional integrated funded-seed candidate

This binds CEDAR's existing `seed_funding.py` selector (PR10000) into the actual
`cloud-execution-lab/integrated_selected.py` agent (PR9997). It adds neither a new
funding model nor another producer. The frozen selected policy and exported
PR9997 archive are unchanged. Source availability is not a whole-game result.

## Run from a repository checkout

```python
import sys
sys.path.insert(0, 'revenue/kaggriculture/cloud-integration-differentials')
from funded_main import make_agent

candidate = make_agent()                 # funding selector enabled
control = make_agent(funded=False)       # original integrated behavior
# Keep one instance per actor/match; do not share producer state between arms.
action = candidate.act(observation, configuration)
```

`funded_main.py` also exposes the usual `agent(observation, configuration=None)`
file-agent entrypoint, resetting its instance at step zero. It expects the normal
repository layout with the sibling `cloud-execution-lab` runtime and its pinned
reference files. This file alone is not a self-contained submission archive.
Like `integrated_main.py`, its lazy factory locates the source from its code
filename; a raw file loader need not populate `__file__` in the entrypoint namespace.

For an existing file-based executor, use these two paths from the same checkout:

```text
candidate: revenue/kaggriculture/cloud-integration-differentials/funded_main.py
control:   revenue/kaggriculture/cloud-execution-lab/integrated_main.py
```

Do not substitute `integrated_parent.py` for that control: it also disables SELL
and therefore does not isolate this funding change. Frozen selected SELL is a
third, separately labeled incumbent benchmark.

To reuse an existing production instance, pass `production=existing_production`.
Call either the returned object's `act` once, or call that producer once and pass
its selected action to the object's `transform`; do not do both for one turn.
The factory accepts the existing `seed`, `committed`, `sell`, and `horizon`
configuration. `sell=False` retains the same optional seed stage while disabling
the existing seller. `funded=False` removes this optional selector, not the
original seed stage.

## Exact integration boundary

The existing selected-action PLANT check and ALDER route-demand calculation run
first, after the current unit stage. Only a demand-valid reduction followed by
an economic order reaches the new optional callback. The callback receives:

```python
seeded, report = seed_queue_selector(
    mechanics, post_unit_observation, selected, proposed, configuration)
```

The state, selected action and proposal are detached copies. The callback contract
is a seed-only action and a report dictionary; `funded_main` supplies the existing
`select_seed_queue` directly. No seed demand, worker route, projection engine or
market simulator is reimplemented. The resulting queue is fed into the same
continuation projection, committed-arrival snapshot and ordered seller that
already consume the ordinary seed-reduced action.

When CEDAR certifies the complete original fixed-price queue from observed cash
without relying on sale proceeds, `seed_reason` is `funded_economic_order`.
Otherwise its original-action fallback retains `later_economic_order`.
`diagnostics['seed_funding']` contains the complete current-market report only
when the optional callback ran. No callback, `seed=False`, demand rejection, and
nondependent queues retain their previous branch behavior. Existing transform
error handling and explicit caller fallback remain in effect.

CEDAR's certificate preserves non-seed execution for the same chosen rival queue
in the current market phase. It does not prove unchanged later controller choices,
terminal cash, independent game wins, or calibrated rival probabilities. Positive
BUY_PRODUCT requests keep the existing unresolved/fallback path. A newly affordable
HIRE in an underfunded original queue remains a rejected seed edit.

## Executed joined evidence

CYPRESS's actual-runtime suite passed 16 methods and 14 official interpreter
transitions in hosted run [34174381218](https://github.com/woahwhattheheck/commons/actions/runs/34174381218),
checkout `ff81687372ac83c3a0684c038fe62cfdedf90dc6`. Zero failures, errors, full
games or new game seeds. This is constructed-state integration evidence, not a
policy-strength or leaderboard result.

The funded 17-to-3 WHEAT-seed case retains the same HIRE and complete non-seed
state in both positions, changing own cash 597 to 737 (+140). After a current
PLANT consumes the final seed, the joined stage retains one seed for future
demand (+160 cash against the original purchase). The underfunded original queue
retains 130 cash rather than the uncertified reduction's 67 and additional HIRE.
Terminal PLACE plus sale remains executable in both positions, with +170 cash
from unused seed purchases. These are separately identified constructed cases,
not independent wins. Actual initial producer calls are one per position.

The exact executed runtime SHA-256 values are:

```text
integrated_selected.py dd6b0b52575ad95a975695d372546ebfbdcb829065574d9c94eab5085a44a9fe
funded_main.py         1b2587bc81533f4cafb9c844d8b5dec1e199460feb8f0a5e0cb7236e8c04ef56
seed_funding.py        d40225f74f37c564dd5e099637defa9dfcf42941fddc5503b60f18fbd2de2302
```

Reproduce the joined tests from the repository root:

```sh
python3 -B revenue/kaggriculture/cloud-composition-cases/cypress/test_funded_join.py \
  --json-output /tmp/funded-join-results.json
```

CEDAR's earlier 15 methods and 71 paired official-market cases are retained as
component provenance, not counted again as these new joined tests. JUNIPER owns
the optional runtime seam and entrypoint; CYPRESS owns the joined test source and
its binding into the existing hosted workflow. The raw run artifact is
`10036744675`, SHA-256 `dbb8977c3394f0c1f857f844222b264981eff8c50761424e5a92b6cec842609d`.

## Next consumer

T08 and the existing executor can freeze this optional candidate against the
integrated control on a separately assigned development shard. That comparison
isolates the funding selector; frozen selected SELL remains a distinct benchmark.
No game seeds, held results, selected default, or upload are changed by this
source delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
