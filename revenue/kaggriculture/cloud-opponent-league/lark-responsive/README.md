# Visible-quote SELL priority opponent

An additive, observation-only stress transform for a frozen league parent. It
sorts adjacent valid SELL orders by descending current public unit quote while
retaining their quantities, duplicates, and stable order for equal quotes.
Every non-SELL order is a barrier at its original index; the engine's executable
market prefix is respected. Unit actions are copied unchanged. The existing
T09 variants and every production agent remain unchanged.

This preserves the parent's issued staffing and production instructions; it is
not a guarantee that the resulting economic trajectory or later parent decisions
remain identical. It is a stress opponent in its parent's lineage, not a new
independent policy family or an automatic competitive improvement.

## Use

Load `sell_priority.py` with the same standard file importer used for the frozen
evaluator, then compose its Actor before starting new games:

```python
variant = evaluator.import_file('/absolute/path/sell_priority.py', 'sell_priority')
evaluator.Actor = variant.actor_class(evaluator.Actor)
# Existing parent specification; its source and dependency closure stay pinned.
opponent = '/absolute/path/parent_adapter.py|sell-priority'
```

Unmarked specifications remain intact. Reuse the existing official file-loader
adapter for the parent. Create fresh actors for each game. Alternatively call
`transform(action, observation, configuration)` inside an existing parent adapter.
The transform reads only `observation.market.prices` and
`configuration.maxMarketOrdersPerTurn`; no history, seed, future shop schedule,
rival action, or private inventory is read.

The Actor wrapper records `sell_priority_enabled`,
`sell_priority_changed_turns`, `sell_priority_transform_seconds`, and
`sell_priority_total_seconds`. Parent call/RPC timings remain distinct from
wrapper timing. The combined parent RPC plus transform must fit the supplied
action deadline; a late transform returns a timeout, never an extra action.
Preserve the existing evaluator's teardown and resource-provenance fields.

## Behavior and validation

```sh
python -B -m unittest -v test_sell_priority.py
```

Eighteen focused checks cover market barriers, all initial HIREs, units,
quantities, prefix truncation, duplicates, stable ties, unquoted/malformed orders,
nonfinite quotes, deep-copy isolation, public-price responsiveness, fresh Actor
counters, intact specifications, combined deadlines and existing failed responses.

The implementation was also exercised in eight completed official-interpreter
full games: two fresh development seeds, both seats, intact-control and transformed
arms. Each game completed 719 action rounds with 720 recorded states. Source
identities remained unchanged; the transform activated and the transformed parent
retained material farm production. Results, complete trajectories, source closure,
actual stdout and the reproducible gate runner are retained in the owner's private
TITAN Library handoff. Those games establish a bounded operational check, not
held-out strength, current-TITAN promotion, or a hosted result. Two mirrored seats
and both arms are not independent seeds. No completed historical panel was rerun.

Gate dependencies: official engine revision
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; current evaluator SHA-256
`f6fbb8a6be911eb3192422e55d687ecd2ffa77315102924393d5144e25c1763a`;
unchanged engine loader `cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e`;
retained source-pack revision `7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f`.
Upstream engine, official adapter and parent licenses remain in that source closure;
this directory does not vendor or replace them. No installation or network request
is performed by the transform.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
