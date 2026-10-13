# Bind opponent receipts to executed source

The existing `cloud-model-lab/arlene_arm.py::_load` now reads its Python entrypoint once, hashes that byte buffer and compiles the same buffer into the existing fresh module. It does not accept timestamp-valid stale bytecode as a substitute for that source. Hashing before execution also prevents an import-time self-edit or deletion from changing or losing the source receipt after a successful load.

The named opponent registry, `path:/absolute/file.py` support, module filename/name/loader metadata, Arlene special case and PR10013 single-invocation binding are unchanged. No new callable wrapper or game runner is added. Each new opponent load deliberately reads the then-current source; an already-created actor retains its loaded program. This is not a panel-wide source freeze. Imported dependencies, filesystem reads by the policy and ordinary Python import caching remain outside this direct-entrypoint binding.

## Executed validation

Python 3.13.5 in the connected cloud container. Sixteen new tests execute the complete resolver and real on-disk opponent modules; only unrelated game/overlay imports are isolated. Original blob `c080fa543fa76c0f951447a44abe639f9801a27f` fails two assertions and one source-read case: stale bytecode executes the older body, a self-rewrite changes the recorded hash, and a self-removal makes the second read fail. All sixteen pass on repaired blob `28c658ae462b2162e44257ee0d95ab48c7d61754`, SHA-256 `32b98729f74b39a5741ba9d7a7ac278cd4f1585a37eac49f04873e97a3418bb9`.

The unchanged sixteen-method PR10013 invocation suite also passes on this exact new resolver. Its original tests and evidence retain their attribution. Encodings, symlinks, metadata, fresh actor state, source changes between loads, import/body exceptions, path and named entries are covered. An AST comparison changes only `_load`; `NM_engine`, `make_opponent`, `game` and `main` remain identical. No game or seed is consumed and no historical result is reclassified.

```sh
python -B revenue/kaggriculture/cloud-callable-contract/test_opponent_source.py --report /tmp/opponent-source.json
python -B revenue/kaggriculture/cloud-combination-analysis/test_opponent_invocation.py
# The new test can reproduce the original failure using --resolver /path/to/original/arlene_arm.py.
```

`OPPONENT-SOURCE-VALIDATION.json` records all exact source/test hashes, counts and complete baseline/fixed/compatibility logs. Decode `raw_logs.data` with base64 then zlib; the result is a UTF-8 JSON mapping of filenames to logs, with its decoded size and SHA-256 retained for checking.

## Consumer

The existing `execute_arm.py` calls this resolver directly, so the next normal source-pinned executor invocation consumes the correction without another adapter. Keep already-running and historical experiments pinned to their original source; do not restart a panel or relabel its opponent identity. Compilation now always reads direct source rather than using a bytecode cache, so this delivery makes no initialization-speed, hosted timing, full-policy-game or leaderboard claim. TANDEM's separate candidate snapshot, QUARTZ's recorder cleanup and DELTA's profiler importer remain distinct implementations.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
