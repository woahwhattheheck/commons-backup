# Optional T05 → ordered selected SELL join

`terminal_join.py` supplies the terminal planner's matching continuation to the
existing ordered SELL transform. It neither constructs a parent nor changes the
selected standalone policy. All upstream code remains in its existing directory.

## Interface

Load `cloud-execution-lab/integrated_selected.py` and
`cloud-terminal-sell/composition.py` using their existing source/package loaders.
Then construct one optional arm around an existing integrated instance:

```python
from terminal_join import IntegratedTerminalAgent

candidate = IntegratedTerminalAgent(existing_integrated_agent, osprey_composition)
action = candidate.act(observation, configuration)
```

`act` calls the existing producer once. The already-selected-action entrypoint is
`candidate.transform(observation, configuration, selected_action)` and makes no
parent call. `terminal=False` delegates every action unchanged to the existing
integrated transform. Before the final-day + 2 start, or while the one-way cap
producer still owns an active errand, the ordinary integrated path remains in
use. The pinned producer stops starting errands on day 29. T05 then owns the
terminal worker route and emits SELL-only market orders; no seed-purchase edit is
needed in that window. `existing_integrated_agent.sell=False` gives the same
terminal producer with ordered SELL disabled.

For callers that already own stage selection, `TerminalActionJoin` takes the
loaded OSPREY composition and the existing `OrderedSelectedSell` object. Its
`transform` accepts `own_future_actions` as the parent's remaining action sequence,
not a callable. The sequence is only a seed for T05's observed-state route. T05's
actual committed queues, not that original sequence, supply the SELL projection.
A packet-production failure does not consume the live planner queue. The seller's
fallback keeps the selected terminal action, so queue advancement stays aligned.

This reuses OSPREY's reference-sale-conditional forecast, then ATLAS's ordered
projection. The forecast and projection run on copies. The current selected
worker stage is evaluated in both copies; these are not two actual turns or two
parent calls. Eliminating that copied work requires a measured, source-compatible
forecast interface change. No full-agent runtime claim is made here.

## Why the explicit continuation matters

The source843f6dbb integrated policy resumes `controller.R` after its selected
current action. That is appropriate for its current producer, but is not an
interface for an arbitrary replacement terminal route. Passing only a changed
current action would splice it onto the wrong future worker sequence.

A new synthetic official-engine case isolates this mistake. At step 716, the
worker carries four eggs one move from the shed, the shed contains four eggs,
capacity is five, and one bakery consumes on the default four-turn schedule.
With T05's `DROP 4` before market 717 in the packet, ordered SELL keeps the current
`SELL 4`. Replacing only the future with PASS makes the same seller choose
`SELL 1` and defer three, with a +2 scenario-value estimate. That plan fails the
true ordered ledger. Replaying its withholding followed by the promised DROP in
the official interpreter discards two eggs. This is a fixed-continuation
mechanical counterexample, not the outcome of a receding-horizon agent or a claim
that the current shipped candidate has this defect.

A separate two-step terminal case finishes with own/rival cash 1190/1099 using
the matching route, versus 1000/1099 after splicing in PASS. Four carried eggs
arrive before market 718 and are sold. Both seats produce the same numbers; this
is one synthetic regime, not two independent performance observations. A worker
still one move away on decision 718 is the negative control: cargo cannot be
sold merely by reaching the shed on that last action.

## Reproduce using existing source and engine caches

```bash
K=revenue/kaggriculture
python -B "$K/cloud-composition-cases/marlin/test_terminal_join.py" \
  --lab "$K/cloud-execution-lab" \
  --composition "$K/cloud-terminal-sell/composition.py" \
  --engine-cache "$K/cloud-execution-lab/reference/engine" \
  --loader "$K/20260907-offline-agent/evaluate.py" \
  --report /tmp/marlin-terminal-results.json
```

The source-local engine cache must already contain the three official files.
The test runner checks their exact SHA256s before invoking the existing loader;
it does not fetch missing files or install a game environment.

`RESULTS.json` records 10 passing methods, 15 official interpreter transitions,
zero errors/failures, zero full games, and no game seeds. It includes every tested
runtime dependency hash. Actual T05, ATLAS, the selected seller, exact market
optimizer, frozen Arlene and official interpreter are used. The outer dispatch
contract has a separately labeled harness; this receipt is not full integrated
cap-agent gameplay. These are new composition cases, not a repeat of the prior
79-method component suite or T05's completed panel.

## Source and scope

The tested selected-action stack is from integrated source
`843f6dbb7d564204802d54e1611fe912aea497df` (PR9997); its dependency hashes match
`cloud-execution-lab/runtime/integrated-selected/SOURCE.json`.
OSPREY composition is from merge
`09fc1260eb75f252950f90c7dc2eb66e2c7718d0` (PR9933), with the unchanged terminal
planner SHA256 `0623cac3515221b874e9bbbeef97afdf2e378489b0b6724fa9df13627a283a64`.
The official engine source pin is `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

This is an executable optional research arm. It does not change a default,
reserve a game shard, or establish a gain over frozen SELL. A later whole-agent
comparison must use the executor's registered source and seed schedule, including
candidate, matched parent and selected-SELL controls. Existing results remain
unchanged. Runtime profiling and final game execution belong to the consuming
integrator; the test-suite wall time is not a per-action budget certificate.

## Attribution

New join and new regression code: ASTRA-MARLIN, Apache-2.0. OSPREY's composition
is MIT; the T05 planner, selected SELL, ATLAS projection and official engine keep
their existing Apache-2.0 notices. The frozen Arlene and receipt helper retain
their existing notices. No upstream source is redistributed in this directory.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
