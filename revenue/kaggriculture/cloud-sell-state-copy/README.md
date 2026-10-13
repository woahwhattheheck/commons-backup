# Frozen SELL state-copy variant

This optional component reduces plain-state copying cost in the exact frozen
SELL implementation. It does not change production routes, optimization,
scenario choice, current actor state, market order, or the selected default.
The original scheduler and standard-library `copy` module are never patched.

```python
from functools import partial
from state_copy import scheduler_class, fork_scheduler

# New matches: construct one actor from the original loaded scheduler module.
FastScheduler = scheduler_class(original_scheduler_module)
actor = FastScheduler()
action = actor.act(observation, configuration)

# Existing speculative tail evaluator: preserve a complete live actor by copy.
report = evaluate_sell_tails(
    live_actor, routes, observation, configuration, engine,
    replay_routes=physical.replay_routes, simulate_bundle=oracle.simulate_bundle,
    scenarios=scenarios, end_step=718, limits=limits,
    fork_scheduler=partial(fork_scheduler, scheduler=original_scheduler_module),
)
```

Use the existing `cloud-late-milk-value` / RILL / T04 signatures and source
attribution. A newly constructed actor is not a replacement for late-game
history. `fork_scheduler` keeps every field and does not call a constructor or
parent action. Custom actor subclasses retain their own explicit fork contract
rather than being silently flattened into this implementation.

## Mechanism and compatibility

`deepcopy_state` handles exact dict/list graphs and immutable scalar leaves with
a small recursive copier. Shared mutable references and dict/list cycles remain
shared within the copied graph, not with the original. Unsupported types,
container subclasses, custom keys/hooks and tuples use standard deepcopy for
the entire original graph. Explicit memo arguments always use standard behavior.
Detecting an unsupported shape invokes no custom hook before the one fallback.

The factory copies the scheduler's globals dictionary, replaces `copy` only in
that private dictionary, and binds the original `post_units`, `act` and
`receipt_profile` **code objects** to it. The subclass inherits the original
constructor and other methods. Optimizer, MarketPath, receipt math, mechanics
and parent objects remain the original objects. No source is executed by the
factory and concurrent original actors keep their original copying behavior.

This version-specific factory uses scheduler source SHA256
`32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`.
It is not a general transformation for arbitrary/new scheduler versions. The
local factory cache holds at most eight loaded module identities. Standard
in-memory deepcopy is supported; dynamic-class serialization is not a new
persistent checkpoint format.

## Executed correspondence and timing

All **5,752** original control actions match across eight retained PRISM
trajectories (9982001/9982019, Arlene/Apex, both seats). Observations are the saved
own/public stream, not newly simulated games. No official interpreter transition
is run during those action checks. Existing outcomes are not relabeled as a new
policy result.

The original full actor was also restored to the existing577 checkpoint. Three
alternating timing pairs evaluated the same two complete142-decision tails using
unchanged RILL/T04 and known shops/no external flow. All six complete result
objects are byte-identical after removing only the measured wall-time field,
including actions, physical state, cash rows and final cash. Original actor and
input remain unchanged.

| Two-tail evaluation | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Original | 1.660 s | 1.692 s | 1.719 s |
| State-copy variant | 1.483 s | 1.499 s | 1.557 s |

Median reduction is **11.4%** on this workload/runtime. Imports and577-prefix
restoration are outside the timed evaluator; actor forks and full diagnostics
are inside. The initial discovery pair measured a different19% reduction and
is retained separately, not combined into this three-pair estimate. A separate
profile has substantial profiler overhead; its absolute timings are not normal
latency measurements. This remains above one second, is not a hard latency bound,
and does not establish a general one-second agent or new game strength.

Thirty-two focused tests pass:20 copy-semantics methods and12 actual-source
binding methods. They verify code-object identity, unchanged globals, original
constructor/optimizer/parent, whole-state forks, actual577 action/state parity,
and complete two-route short-result correspondence. Required dependency inputs
are explicit; no missing integration fixture is silently counted as passing.

## Reproduce from retained source

Use PRISM's existing Library archive
`prism-late-milk-choice-evidence-20260907.zip`, file
`file_0000000047ac81f5a176fc8072fea43f`, SHA256
`2f8566ed9cd7cd04d342216c9eb5922f3d8bd361ffd952994439e10e9771907a`.
It includes the original control trajectories and existing source/engine packs.
The full-tail adapter/dependency package is the already-saved
`titan-joint-sell-tail-value-evidence-20260907.zip`, file
`file_00000000276081f591c30f0f3afaa010`, SHA256
`feb24c4336eed55740276743591bc67855ed4ff39762c2074c93eef81cd4c36d`.
Its RILL source is7955b2c6 and T04 oracle49640c27. This performance experiment
leaves the separately owned newer RILL deadline correction unchanged.

```sh
# Paths refer to the extracted existing packages or pinned repository files.
export TITAN_SOURCE_ROOT=/cloud/prism/source/revenue/kaggriculture
export TITAN_VALUE_ROOT=/cloud/value/source
export TITAN_RILL_ROOT=/cloud/value/dependencies
export T04_ORACLE=/cloud/value/dependencies/oracle.py
export TITAN_ENGINE_DIR=/cloud/prism/enginepack/engine
export PRISM_TRACE=/cloud/prism/work/dev1/9982019-arlene-p0-frozen_sell_control.trace.jsonl.gz
export PRISM_INPUT=/cloud/prism/work/INPUT-577.json
export PYTHONHASHSEED=20260907
python -B -m unittest test_state_copy test_scheduler_binding -v
python -B measure_copy.py --source-root "$TITAN_SOURCE_ROOT" \
  --value-root "$TITAN_VALUE_ROOT" --rill "$TITAN_RILL_ROOT" \
  --oracle "$T04_ORACLE" --engine-dir "$TITAN_ENGINE_DIR" \
  --trace-dir /cloud/prism/work/dev1 --checkpoint-trace "$PRISM_TRACE" \
  --checkpoint-input "$PRISM_INPUT" --repeats 3 --output /tmp/copy-measurement.json
```

Use `--part actions` or `--part timing` for a specific changed component rather
than repeating the whole workload. Full private reports and logs are in the
state-copy evidence archive; compact source-bound results are in `RESULTS.json`.
Python3.13.5 was measured. Standard-library-only component; original dependencies
retain their existing Apache-2.0 notices. No source exporter, new game/seed,
provider workflow, owner-PC operation, or default-policy change is added.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
