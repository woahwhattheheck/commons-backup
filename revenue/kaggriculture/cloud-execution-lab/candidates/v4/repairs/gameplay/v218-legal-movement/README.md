# V218 legal movement and shed access

This is one source repair inside canonical `main:candidates/v4`, not a new agent, runtime entrypoint, gameplay key, release archive or V4 branch. It is not imported or activated by production.

## Mechanism

Official engine Git blob `3c202c7ee921da239356789e266b694635103fc4` allows movement onto LOCKED tiles. Its shed PICKUP/DROP/PLACE handling also precedes the LOCKED tile-operation guard. Farming a LOCKED tile remains illegal. V218's `_v218_path` incorrectly rejects legal transit, and `_v218_plan` unnecessarily excludes locked shed-access corners.

The repair removes exactly those two ownership filters. It preserves board bounds, plan 2, callback 712 admission, the fertilizer price-1 condition, empty/idle worker checks, pending/native tape guards, unique target allocation, the 100-unit capacity bound, the seven-callback route limit and a real final DROP. `transform(source)` is exact identity; applying the repair requires the literal `enabled=True` or explicit CLI flag. CLI output must be a new file, never the input or an existing file.

Six component source hashes are checked before any enabled transformation: FarmView, V218 path, routes, capacity bound, planner and executor. Double application or source drift fails closed. The correction must not be used to silently absorb the independent V218 multiplan change: a changed planner needs a separately reviewed repin.

## Executed evidence

Exact source `88abf4fd6c44f3ff938cede8815aeb58085eaace`, test `afb5d068976112eb1e2e05ac5b1bb0b0df432df6`, and mutation runner `1ee3e4ec2b105c363258e31e99ad09314c93f964` were executed with Python 3.13.5 normally and under `-O`.

Each mode passed 14 tests with no failures, errors or skips. Across all four legal quadrant-unlock prefixes, 40,000 start/end movement cases matched the actual engine; all 18,750 previously accepted paths stayed byte-identical and 21,250 previously rejected paths became legal. These are movement checks, not counts of profitable game opportunities.

The full-interpreter terminal grid contains 600 paired constructed cases: both seats, four shed-corner worker starts, 25 NW target locations, and stock levels 0/99/100. Twenty-four cases improved cash by exactly one unit (12 per seat); the other 576 had equal cash. No tested case lost cash, and all candidate routes had zero aborts. A boundary witness drops fertilizer on callback 718 and the unchanged parent SELL settles it in the same callback. Five behavioral mutations are rejected in both modes: restored LOCKED transit, lost board bounds, removed DROP, relaxed capacity, and lost collection.

These are pinned V218 components and the full official engine, with synthetic parent tapes and constructed state. The external seed resolver is a scoped fixture shim; the engine's mechanics, markets and terminal handling are not mocked. Runtime source transport was historical router `21c4f1db0298f8955b1f5ad366bd780a89cad206`; the relevant current a3e2 component source was read back, but the whole current router was not materialized or executed here. The report explicitly distinguishes input custody from whole-router execution. This is NOT a complete current-runtime, natural-activation, full-game or leaderboard gate.

## Reproduce

Set `TITAN_ROUTER` to the exact canonical donor a3e2 file, or to the explicitly named historical fixture. Set `TITAN_ENGINE` to the exact official `kaggriculture.py`, with adjacent `kaggriculture.json` blob `b354d06b742fe48402513792253f1a5c29366b20`. No network or external Python packages are required.

```sh
python test_v218_movement_parity.py > result-normal.json
python -O test_v218_movement_parity.py > result-optimized.json
python run_mutations.py
python -O run_mutations.py
```

`execution-logs.tar.gz.b64` preserves all six exact stdout/stderr result files, including complete witness traces. Decode base64 to gzip; verify SHA-256 `3d1ba96d9e114ed082b17d37105fc8acdc33a0d250c12a186f8f842045428501` before extracting. Every member's byte count and digest is recorded in `MANIFEST.json`.

## Integration boundary

Consume these two predicate changes through the existing V218 owner in the ONE canonical V4. Do not overwrite shared donor router a3e2, invalidate other lanes' source pins, create another feature key, or run the old `apply_v4.py` against current production. Re-run the component oracle with exact current input, compose into the current ABI, and measure natural activations and full-stack interactions before any activation. The constructed +1 recovery is not a universal-profit or strength claim.
