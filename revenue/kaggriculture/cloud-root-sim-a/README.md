# ROOT-SIM-A full-game comparison

This additive consumer composes job files for the existing
`cloud-ultra-league/run_league.py` trajectory driver and aggregates its completed
official-engine games. It does not implement another engine or evaluator.

Operation `titan-root-sim-a-20260908-1345` ran seeds 1909081401–1909081432,
both seats, against frozen Apex, Arlene, and Euler. The controllers were exact
archive `499989ab…` and unchanged hosted-v1 control `7b58fa06…`. The canonical
bank contains 384 full games at 720 configured steps (719 action rounds), with
no controller errors or timeouts after setup correction.

Across 192 games per controller, each recorded 188 wins and four losses. Current
improved matched paired margin over v1 in every opponent stratum: +12.09 cash
per seed against Apex (95% seed-bootstrap CI 10.66–13.75), +13.00 against Arlene
(10.50–16.16), and +19.53 against Euler (10.00–38.16). The seed-stratified
three-opponent mean delta was +14.88 (10.92–21.67). This is a development bank,
not a hosted-rank estimate.

The first Apex attempts compiled its unchanged C++ policy inside the first
one-second action call and timed out. Its source-supported build command was run
once in the frozen job directory; those eight attempts remain setup failures and
the fixed cells have explicit `setup-fixed` identities. Four current cells in a
later localized four-game contention burst were likewise retained and repeated
at one-game concurrency with explicit `low-concurrency-fixed` identities. Twelve
setup failures are excluded from W/D/L and paired inference.

`RESULTS.json` contains aggregate cash, W/D/L, seed-paired confidence intervals,
action/RPC timing, exact source hashes, and job-config hashes. Raw trajectories,
per-game results, and failure packets remain in private project storage.

Usage:

```sh
python3 -B prepare_jobs.py --repo /abs/commons --job-root /abs/job \
  --phase calibration --jobs 2
python3 -B /abs/commons/revenue/kaggriculture/cloud-ultra-league/run_league.py \
  --config /abs/job/configs/calibration-current499989ab.json
python3 -B analyze_results.py --repo /abs/commons --job-root /abs/job \
  --output RESULTS.json
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
