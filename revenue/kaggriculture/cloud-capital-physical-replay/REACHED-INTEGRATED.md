# Complete integrated continuations from a retained decision-226 input

`reached_integrated.py::fork_integrated` supplies the documented original
IntegratedSelectedAgent/PlanOverlay family to JOINT's existing complete-actor
consumer. It copies the entire actor graph, preserving the one shared controller
inside production and its chooser, while sharing only the three existing source
modules. No simulator, selector, route generator, controller reset, or replacement
of the selected policy is added.

## Executed natural-input comparison

The input is TRACE's retained DELVE development 9965001, seat 0, funding OFF and
SELL ON. The original actor is restored through decisions 0–225; every one of its
226 actions matches the saved expected action. All 29 runtime source-map entries
match, including the original certificate import. This is not the missing HAZEL
9956003/4 state or WIDEFIELD 9921001.

At the checkpoint, own cash is 8 and there are nine hands. The visible shops are
BRUNCH_SPOT, BAKERY and PIZZA_SHOP. The original market queue is SELL WOOL8,
BUY_PRODUCT WHEAT3, BUY_ANIMAL GOOSE1. The alternative changes to the existing
complete SHEEP route before the one authoritative action. It is not an isolated
animal-purchase substitution.

Both complete copied actors execute through decision 718 with the unchanged T04
owned-state oracle, KESTREL's completed-return deadline correction, and JOINT's
existing SellRouteView. The hypotheses intentionally match OSPREY's prior
natural-input quote comparison:

| Declared future | MAIN final own cash | SHEEP final own cash | SHEEP minus MAIN |
| --- | ---: | ---: | ---: |
| Keep current shops; no new buyer or rival flow supplied | 89,291 | 84,040 | -5,251 |
| Add hypothetical YARN_STORE first visible at 288; no rival flow | 109,492 | 118,750 | +9,258 |

The same restored checkpoint starts every branch. The future buyer is an explicit
hypothesis, not an observed feature at 226. Holding future shops fixed is a model
assumption, not a prediction that the real environment stops revealing shops.
T04 represents external changes before our market and freezes rival public farms;
it does not execute a responsive opponent's simultaneous market or worker actions.
Rival cash and win utility are therefore unknown.

All four canonical continuations finish: 1,972 modeled decisions. No discarded
stock is reported. Within each route, both hypotheses have identical full actions
and recorded queue/market rows through 287. The first recorded market-row change
is 289; the first action difference is 293. There are 35 action differences for
MAIN and 38 for SHEEP. Thus the integrated SELL response is preserved rather than
assuming one immutable sale tape across futures.

DATE's unchanged completed-outcome ranker reconciles all 1,972 queue rows and
retains MAIN over the full two-hypothesis bank: the worst paired SHEEP change is
-5,251. This is a conditional own-cash comparison, not a calibrated probability,
a general policy recommendation, or a new full-game result. No live actor is
changed by the ranking call.

The corresponding scheduled-volume OSPREY values were -5,042 and +8,807. The new
physical deltas differ by -209 and +451 respectively. This is a difference between
complete execution and nominal scheduled-volume models, not a claim about the
cause of those differences or an actual paired-game improvement.

## Accounting and limitations

The first shared 30-second diagnostic batch completed one case, then stopped
partway through the second. Its complete case was reused; its incomplete case and
two unstarted entries are retained. The three remaining canonical cases completed
in separate bounded shards, taking 18.376, 14.730 and 18.746 seconds locally. There
were four complete continuations and one partially executed continuation, not five
complete games. Across those attempts, 2,314 modeled decisions started and 2,313
market stages completed; the canonical bank contains 1,972 of them. The initial
partial attempt remains unscored. These costs are far beyond a one-second action
budget: this delivery is an offline economic consumer, not a runtime promotion.

The final CLI was also exercised in completed-report reuse mode: it restored the
226-action prefix, reused all four completed cases, and invoked DATE without new
engine/model decisions. Its zero new tail time is not total experiment time.

Sixteen actual-source tests pass, including complete mutable-graph isolation,
preserved module references and controller aliases, expected first action,
complete-route switching, malformed prefix/private-seat detection, and existing
DATE handling of partial/missing outcomes. This is the same 16-method suite
executed before and after final consumer-provenance labeling, not 32 methods.
No old peer suites, scored game panels, held seeds, or provider workflows were run.

## Reuse

Use JOINT's existing API with this family's explicit fork:

```python
from reached_integrated import fork_integrated

report = evaluate_sell_tails(
    restored_integrated_actor, (MAIN, SHEEP), observation, configuration, engine,
    replay_routes=physical.replay_routes,
    simulate_bundle=oracle.simulate_bundle,
    scenarios=declared_scenarios, end_step=718,
    limits=physical.ReplayLimits(seconds=diagnostic_budget, decisions=1972),
    fork_scheduler=fork_integrated,
)
```

The actor must already be restored through its actual prefix. `state_digest` is a
fingerprint of the instance graph, not a serialized checkpoint. Source modules
are named, not copied into that fingerprint. Unknown actor families are not
silently converted to an Arlene-only actor.

The CLI consumes existing extracted inputs; no new source export is necessary:

```sh
PYTHONHASHSEED=20260907 python reached_integrated.py \
  --runtime "$ORIGINAL_RUNTIME/revenue/kaggriculture" \
  --trace "$TRACE" --replay "$KESTREL/physical_replay.py" \
  --oracle "$JOINT/dependencies/oracle.py" \
  --tail "$JOINT/source/sell_tail_value.py" \
  --evaluator "$DELVE/source/tree/revenue/kaggriculture/cloud-eval/evaluate.py" \
  --engine "$DELVE/engine/engine" --date "$DATE/cloud-capital-scenarios" \
  --seconds 35 --max-cases 1 --output shard-1.json
```

Add `--resume shard-1.json` with a new output path for subsequent shards. Completed
cases are reused only against the same source map, observation, scenario bank,
horizon and program identities. Partial cases are not scored or reused as complete.
A final `--max-cases 0 --resume complete.json` consumes saved outcomes without new
model decisions. The per-case cooperative budget cannot preempt a dependency.

Create ORIGINAL_RUNTIME as a separate cloud copy of DELVE's runtime tree. Only
in that new copy, restore `cloud-integration-differentials/seed_funding_original.py`
to the original import name `seed_funding.py`; do not overwrite the archived source.
The CLI verifies this original closure against TRACE's SOURCE-MAP.json. Start it
in a fresh process so foreign imports do not substitute for the retained actor.

Existing Library inputs: DELVE `file_000000008fe481f58309a3cfde721385`, TRACE
`file_000000002b4081f5a9f64c39a5a19bbc`, KESTREL
`file_00000000f73081f59dab172941ef8f6b`, JOINT
`file_00000000276081f591c30f0f3afaa010`, and DATE
`file_000000001aa081f58471dfcdd39ec8e8`. Their archive hashes are in the result
manifest. Existing engine and upstream licenses remain with those sources.
New files are Apache-2.0 under the repository license.

The separate delivery archive retains full final and intermediate reports,
initial partial evidence, execution logs, the exact sharded driver, new source and
tests, TRACE inputs, and the consumed runtime/dependency files with source hashes
and notices. The first batch's original orchestration file was not separately
saved; its raw evidence and complete dependency identities are retained. No new
simulation is needed to inspect these results. The committed JSON is a compact
index, not a claim that all raw observations are embedded in the repository.

From the extracted `titan-rill-reached-integrated-20260908.zip` delivery root:

```sh
RILL_REACHED_ROOT="$PWD" PYTHONHASHSEED=20260907 python -m unittest discover \
  -s work/revenue/kaggriculture/cloud-capital-physical-replay \
  -p test_reached_integrated.py -v
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
