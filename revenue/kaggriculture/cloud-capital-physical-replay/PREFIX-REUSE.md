# Reuse identical conditional prefixes

The existing `replay_routes` callable now accepts `reuse_scenario_prefixes=True`.
The default remains the original independent per-route/per-scenario execution.
This opt-in reduces repeated physical simulation; it does not select a route,
alter the canonical TITAN package, or supply a new market/production model.

## Call and supported execution

Pass the whole declared scenario bank in ONE existing call:

```python
report = replay_routes(
    controller, route_ids, observation, configuration, engine,
    oracle.simulate_bundle, scenarios=scenarios, end_step=end_step,
    fork_controller=existing_complete_actor_fork,
    limits=ReplayLimits(seconds=120, decisions=5000),
    reuse_scenario_prefixes=True,
)
```

The numeric limits above are caller settings, not a one-second runtime claim.
Calling separately for each scenario cannot share work. Existing JOINT callers
may supply `functools.partial(replay_routes, reuse_scenario_prefixes=True)` at
its existing replay injection point, retaining their original full-actor fork.

Use the unchanged deterministic T04 oracle and its explicit Scenario fields:
`market_deltas`, `new_shops`, `new_weeds`, and descriptive `label`. Additional or
unknown scenario shapes use ordinary execution. The common boundary is the last
WHOLE decision before the first different scenario event. An EOD shop insertion
at287 ends sharing at286, not288. Different labels alone do not affect mechanics.
Only the common prefix across the ENTIRE supplied bank is reused; no scenario
is omitted or weighted. Later branches are not recursively grouped.

The checkpoint contains an independent complete controller plus T04's returned
own farm, private inventory, market and town. It preserves controller aliases,
ongoing sales and any public-feature route switch that happened during the
prefix. The next view retains the original observed rival farm and advances its
clock. No opponent-private world, RNG draw or mid-turn snapshot is invented.
Any actor-local generator must be included by the supplied complete fork.
External/global randomness or stateful simulator callbacks are outside this
opt-in contract. The tested integrated actor and invoked T04 primitives are
deterministic under their supplied explicit scenarios.

Suffix execution calls the SAME T04 oracle. Cash ledgers, consumed/discarded
stock, labor, action maps and recorded market queues are joined, not repriced.
Every case retains a detached complete original-schema result. The outer report
adds `prefix_reuse`; `decisions_executed` counts only actually executed decisions.
The existing cooperative deadline checks still apply after simulation, checkpoint
copying and result encoding. Partial prefixes, suffixes and overdue returns stay
unscored; BaseException cancellation propagates. This does not preempt a blocked
dependency or promise a hard wall-time bound.

## Executed evidence

26 new methods and11 existing completion-deadline methods pass. New coverage
includes actual pinned T04 both-seat correspondence, pre-market and EOD events,
changed active routes inside a common prefix, complete actor-local RNG copying,
independent evidence, exact default schema, and incomplete/cancelled work.

The natural comparison consumes RILL PR10220's already-retained DELVE226 input and
full integrated actor. All226 saved prefix actions restore exactly, with zero
engine calls for restoration. The new shared execution matches ALL fields of the
four original complete-case records: actions, active routes, market queues,
physical states, cash and auxiliary receipts. Original live actor and input stay
unchanged. Actual modeled decisions fall from1972 to1850, eliminating122 (61 per
route). New local full-bank time is59.359s; no repeated original natural timing
bank was run, so no causal natural-case speed percentage is claimed. This remains
offline diagnostic work, not a one-second agent or new game-strength result.

A separate constructed workload uses the retained board with an explicitly
changed22-70 clock, two scripted controllers and eight declared future flows.
Five alternating old/new pairs produce identical complete results. Each original
call executes784 decisions versus420 with reuse. Median whole replay-call time
is580.061ms versus320.775ms (44.7% lower), excluding imports. These are local
component timings on sixteen constructed cases repeated for timing, not public
opponent games, statistical wins or a full-agent latency claim. Raw samples and
source/engine identities are in PREFIX-REUSE-RESULTS.json.

## Reproduce without a new game or transport workflow

Use the existing private `titan-rill-reached-integrated-20260908.zip` announced in
T06, SHA256 `6f0b1db42c16ded162c748911167e97e9cbdcc16317d5b4f843e0b7d18e9b16e`.
Extract it as one evidence root; its191 payload hashes were verified before use.
It already includes the original actor, engine, T04 and saved report. No network
or new engine download occurs in these commands. Run from this source directory:

```sh
OSPREY_RILL_EVIDENCE=/path/to/rill-evidence python -m unittest -v test_prefix_reuse.py test_completion_deadline.py
PYTHONHASHSEED=20260907 python -B check_prefix_reuse.py --rill-evidence /path/to/rill-evidence --output /tmp/new-prefix-result.json
python -B benchmark_prefix_reuse.py --rill-evidence /path/to/rill-evidence --output /tmp/new-prefix-timing.json
```

Without the evidence variable, the native methods are explicitly skipped and the
pure boundary methods still run. The natural command restores the original actor
from its ordered own-input stream; it never creates a new actor at226. Original
RILL report/economic conclusions, DATE/FLOW/PRISM work, selected policy, existing
game seeds and canonical submission remain unchanged. New files retain this
directory's Apache-2.0 attribution; dependency licenses stay with the input pack.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
