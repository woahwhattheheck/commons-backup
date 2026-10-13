# TITAN checkpoint58f8e6c1: 12 current-package games

Exact archive `58f8e6c1808a28ad659e763e9d47ce45e566bc16d9248e28c9c2764f9ad66062` (278337 bytes), merge `9db2f2f94666b3ca126f97ab98d28f9a3814de4f`, source PR10167 `0600baffd560e5f4299eb034eca65f7f2e2e5bcd`. CURRENT was resolved once before running and matched the requested archive. Embedded SOURCE.json hash `ab1704734b4082af14e322dfa3f32a5440f6a22338dd65530c52845604bca4c4`; all73 runtime files verified before and after games. Archive was extracted into a fresh standalone directory, with safe member checks. No repository policy imports or package edits.

**12 original games completed:12W/0T/0L, zero errors/timeouts.** No retries, ancestor panels or held sets were run. Six fresh development seeds were claimed in T09 before execution: two per opponent, each both seats. Five of six pairs have identical own/rival cash; mirrors are dependent.

| Opponent | Seed | Candidate seat | Own cash | Rival cash |
|---|---:|---:|---:|---:|
| frozen-sell | 9924001 | 0 | 90889 | 90649 |
| frozen-sell | 9924001 | 1 | 90889 | 90649 |
| frozen-sell | 9924002 | 0 | 132245 | 132005 |
| frozen-sell | 9924002 | 1 | 132245 | 132005 |
| apex | 9924003 | 0 | 149435 | 141949 |
| apex | 9924003 | 1 | 149435 | 141949 |
| apex | 9924004 | 0 | 81462 | 75343 |
| apex | 9924004 | 1 | 81462 | 75343 |
| cok10 | 9924005 | 0 | 100432 | 75615 |
| cok10 | 9924005 | 1 | 100432 | 75687 |
| cok10 | 9924006 | 0 | 128300 | 109278 |
| cok10 | 9924006 | 1 | 128300 | 109278 |

Frozen SELL opponent mean own111567/rival111327; all four margins+240. Apex mean own115448.5/rival108646. COK10 mean own114366/rival92464.5. These are actual head-to-head checkpoint results, not paired deltas against separately rerun ancestors or a hosted-rank prediction.

8628 candidate actions: externalRPC mean5.467ms,p95 14.655ms,p99 27.176ms,max333.516ms. Child wall max323.917ms and child CPU max323.751ms. Max cold step0 externalRPC 87.040ms. Quantiles are nearest-rank across individual actions. All actions, returned CPU/wall, outerRPC and raw evaluator results are retained. The wrapper captures full observation/config on a failed request, but none occurred; internal runtime stage/fallback diagnostics are not exported and no zero-fallback claim is made.

Configuration: consumer=frozen,seed=true,funding=true,terminal_route=false,terminal_history=false,committed=true (ordered-only),budget_seconds1.0,reserve_seconds.01. Official engine28b6d8af with existing evaluator.Actor/play,1sRPC/10sstartup/120sgame, one worker. FrozenSELL opponent is the accepted exact scheduler32c8610c via its unchanged wrapper; Apex and COK10 retain bank source identities in originals and the existing source-freeze.json. No opponent source changes.

run_checkpoint.py is a scoped consumer of the existing evaluator; summarize_checkpoint.py summarizes its originals. Full records and SOURCE.json are in the bundle described by bundle.json; concatenate listed binary parts and verify its SHA256 before extraction. All computation ran in existing cloud VM/task https://chatgpt.com/c/6a9f4095-0eac-83ea-adc2-ac11f4e09613 . Root owns checkpoint submission; no duplicate Kaggle write, runtime repair, new VM or spend. T08/root received early completed shard and final12-game scores before publication.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
