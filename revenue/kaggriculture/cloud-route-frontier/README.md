# Ordered route frontier and exact segment composition

Reusable Python component for completed, caller-supplied macro routes. It keeps
cash/deadline tradeoffs, composes only matching route boundaries, and exposes
completed macros to the existing T06 search kernel. No existing controller,
selection default, seller, source exporter, or workflow is changed.

## Runtime interface

`route_frontier.py` is standalone standard-library code, with no engine, policy,
network, or model import. Python 3.10 or later is needed.

```python
from route_frontier import (
    Alternative, BoundRoute, exact_key, kernel_model, pareto_frontier,
    rollout, splice,
)

# advance returns the next COMPLETE planning state. It receives private copies.
# The caller supplies a bounded pure transition and the already-selected actions.
route = rollout("collect", observed_state, selected_actions, advance,
                context=exact_key({"engine": engine_pin,
                                   "configuration": configuration,
                                   "scenario": causal_scenario}),
                max_steps=24)

# A suffix is generated from the actual prefix exit, not an old controller tape.
suffix = rollout("deliver", route.state(), continuation_actions, advance,
                 context=route.context, max_steps=24)
complete = splice(route, suffix)

# The selected trace persists; the caller still owns its valid fallback.
live = BoundRoute(complete)
action = live.act(current_observable_state, supplied_fallback)
```

State and action inputs are finite JSON values with string mapping keys. Include
time, relevant controller state, cash, worker positions, tiles, flags, inventory,
and any other field that affects continuation. Mapping insertion order is
preserved: sorting carried goods can change which product survives a DROP into
a nearly full shed. Conservative ordering also keeps some semantically equal
maps separate; it never equates different ordered inventories.

`Trace` stores immutable ordered snapshots. `state()` and `action()` return fresh
objects. `splice` requires an exact ordered prefix-exit/suffix-entry and the same
transition/configuration/scenario context. There is no automatic WAIT, worker
reset, input substitution, or stale suffix recovery. The caller can generate a
new continuation from the real state, as the executed recovery case does.

`BoundRoute` checks the same complete observable representation used to plan.
Repeated identical observations return the same action. A mismatch keeps the
supplied fallback unchanged and does not resume the old trace. Full two-player
states in the evaluator are **not** runtime observations: no opponent-private
state or future replay action may be supplied to a live policy through this API.

## Pareto alternatives

Create an `Alternative(name, traces, objectives, values)` with one completed
trace and objective vector per explicitly named scenario. Every objective is
maximized; express costs with a negative sign when appropriate. Scenario order is
aligned by context, not averaged. A higher mean cannot cover a loss in another
included scenario.

By default, exact dominance compares only equal objective definitions, scenario
sets, entry states, macro lengths, and **complete exact exit states**. Different
cash, stock, worker, or controller exit states remain incomparable. This is
intentionally conservative: the component does not assume that more inventory
or more cash makes every continuation feasible.

A caller can supply `continuation_keys` and a descriptive `equivalence_label`
when it has independently established a weaker continuation equivalence. This
is a stated assumption, not something the library proves. The fixed terminal
case uses `("DONE",)` and `"terminal-no-continuation"` because no further action
exists and only final cash remains valuable. Do not reuse that label midgame.

`pareto_frontier(alternatives, max_size=64, max_candidates=256, rank=None)` returns
`kept`, exact `dominated` pairs, `budget_dropped`, and a comparison count. The
candidate limit rejects excess input rather than silently truncating it. A size
cap applied after exact dominance is explicitly approximate. An optional caller
ranking only chooses among these cap removals; it does not become an exact
dominance rule. Without a rank, stable input order is used and recorded.

To choose a route under an actual intermediate cash deadline, filter the retained
alternatives by cash available at that deadline before ranking final cash. The
engine case demonstrates why ranking final cash alone loses this alternative.

## Existing T06 consumer

```python
import search_kernel                 # existing ../cloud-search-kernel source
model = kernel_model(search_kernel, completed_traces,
                     evaluate=lambda state, scenario: terminal_value(state))
result = search_kernel.search(
    model, scenario_states, scenario_contexts, fallback_macro_name,
    limits=search_kernel.Limits(seconds=0.05, max_transitions=2000, max_depth=2),
)
```

One macro name must carry the **same complete ordered action sequence in every
scenario**. Receipts may differ, but the adapter cannot choose different plans
using a hidden scenario label. Cached transitions require exact context and
ordered entry-state matches. Missing transitions are infeasible, not fabricated.
A search depth counts complete macros, not individual turns: evaluate actual
state timestamps and compare coherent horizons. Selected-action execution stays
with the caller or `BoundRoute`; the adapter does not invoke a parent controller.

Trace generation is bounded by `max_steps`, and frontier comparison by the
candidate limit. Those are work-count bounds, not wall-time guarantees. Pure
callbacks, scenario completeness, candidate generation, live fallback validity,
objective completeness, and any declared continuation equivalence remain caller
responsibilities. This is not an opponent predictor or a whole-game policy.

## Executed evidence

29 regression methods pass, including 126 enumerated four-point frontier sets,
mutation isolation, state/context mismatches, explicit approximate truncation,
and the actual unchanged T06 module with two scenarios. No methods were skipped
in the recorded run.

`engine_cases.py` executes the pinned official interpreter in both positions.
The 34 retained traces contain 50 recorded transitions, not 34 full games. All
states, actions, source hashes, and the actual consumer outcomes are retained.

| Fixed integration case | Result in each position |
|---|---|
| Early versus late sale | Early 318; late 352, but 0 available at the earlier deadline. Both routes survive; the 100-cash deadline chooses early. |
| Wrong-position suffix | Naive splice realizes 0; exact composition rejects it. Rebuilding a return-and-drop continuation realizes 318. |
| Missing seed | Naive PLANT leaves the tile empty; incompatible suffix is rejected. |
| Ordered inventory | Equal sorted carried counts produce 160 versus 200 after capacity-limited DROP. Ordered keys distinguish them. |
| Exact endpoint comparison | A zero-profit SELL/BUY and idle finish at the same state and cash 100; the former exposes more intermediate liquidity. This is not a profitable cycle. |
| Final market boundary | Sale on the last executable turn realizes 318; attempting a transition after DONE is rejected. |
| Actual T06 adapter | Chooses the late macro without an intermediate cash constraint, value 352, two transitions and two cache hits. |

These are deterministic synthetic integration cases with a declared PASS rival,
not complete-game win/tie/loss evidence, an opponent-strength result, or grounds
to change the selected TITAN policy. No new game seed, full panel, Kaggle write,
owner-device execution, or source transport job was used. Timings in
`engine-results.json` are local samples, not a whole-agent or worst-case bound.

## Reproduce offline

Reuse existing engine artifact `10005621438` from Commons. Supply the directory
containing `kaggriculture.py`, `kaggriculture.json`, and `utils.py`. They are pinned
to [Kaggle/kaggle-environments commit 28b6d8af](https://github.com/Kaggle/kaggle-environments/tree/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c).
The evaluator checks all three hashes and loads the original interpreter and its
original `resolve_episode_seed` helper. It does not initialize a random game.

Run inside this directory:

```sh
T06_KERNEL_FILE=../cloud-search-kernel/search_kernel.py \
  python -m unittest -v test_route_frontier
python engine_cases.py --engine-dir "$ENGINE_DIR" \
  --kernel-file ../cloud-search-kernel/search_kernel.py --output replay-results.json
python -m py_compile route_frontier.py engine_cases.py test_route_frontier.py
```

The actual T06 consumer used Git blob
`d05b35057509ed706679c0c841a81ffba05a9936`, unchanged. `engine_cases.py` checks that
pin when `--kernel-file` is supplied. Omitting the argument explicitly records
`not_run` for the consumer; it is not a passing integration claim. Unit tests
skip their consumer class when no T06 module is available; the recorded 29-test
run supplied it and had zero skips.

Read the complete retained evidence without running a simulation:

```python
import base64, gzip, hashlib, json
from pathlib import Path
report = json.loads(Path("engine-results.json").read_text())
compressed = base64.b64decode(Path(report["trace_archive"]["file"]).read_bytes())
assert hashlib.sha256(compressed).hexdigest() == report["trace_archive"]["gzip_sha256"]
raw = gzip.decompress(compressed)
assert hashlib.sha256(raw).hexdigest() == report["trace_archive"]["raw_sha256"]
traces = json.loads(raw)
assert len(traces) == 34
```

See `validation.json` for commands, counts, and file hashes. Existing engine,
search, producer, seller, and policy source remains under its original ownership
and license; see `NOTICE.md`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
