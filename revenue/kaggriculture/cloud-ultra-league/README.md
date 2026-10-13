# Full-game league consumer

`run_league.py --config /absolute/path/job.json` composes the existing official
evaluator with compressed transition records, complete call/RPC timing samples,
per-game checkpoints, and a read-only joint-action audit. Each game runs fresh
isolated actors. The initial eight cells complete before the remaining cells
launch. A cell is never retried automatically.

Configuration fields: `candidate`, `opponents` (label to callable path), `cells`
(objects with `id`, `seed`, `seat`, `opponent`), `engine`, `loader`, `evaluator`,
`output`, `rng_seed`, `action_timeout`, `startup_timeout`, `game_timeout`, `jobs`.
Use absolute paths, freeze the complete input closure, and keep generated records
in the designated private destination. Both seats are separate executions of the
same seed, not independent environment draws.

To consume the unchanged LARK opponent wrappers, add explicit frozen module paths:

```json
"lark_wrappers": {
  "sell_priority": "/absolute/path/lark-responsive/sell_priority.py",
  "pressure_priority": "/absolute/path/lark-responsive/pressure_priority.py"
}
```

Use `/absolute/parent.py::agent|sell-priority` for visible-quote ordering or
`/absolute/parent.py::agent|supply-pressure` for the public-curve pressure proxy.
Unmarked specifications keep their parent actions. Without `lark_wrappers`, the
existing Actor path is unchanged. The pressure wrapper receives the exact loaded
engine's `market_price`; freeze both wrapper files with the rest of the inputs.
With this option, module paths must be absolute and each actor may have only one
supported terminal marker. Invalid or stacked markers fail before cells launch.
Detailed parent call/RPC samples and LARK activation/change/transform timing
fields are retained. Parent RPC plus the selected transform share the supplied
action deadline, checked after the transform returns. This does not preempt a
transform. Change counters include changes later rejected by that deadline;
parent call/RPC arrays exclude transform time. These are opponent stress modes,
not canonical-policy changes.

`duplicate_harvest_targets(observation, action)` reports co-located actors
assigned the same harvest target using the player's visible observation. It
does not mutate a route or estimate the value of another action.

Run the synthetic engine checks with:

```sh
python test_selected_action_audit.py --loader-path /path/loader.py --engine-dir /path/engine
python test_run_league.py
```

The existing engine and evaluator retain their upstream licenses. No competitor
source, recorded match data, or generated job configuration is included here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
