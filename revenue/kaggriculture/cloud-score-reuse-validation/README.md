# Existing-score reuse regression consumer

This directory publishes two previously completed ELM regression scripts for the
existing `selected_sell_core.MarketPath.score` reuse direction in QUICKSTEP
PR #10518. It does not add an optimizer, modify the canonical runtime, or create
a release gate. WIDEFIELD and the current performance consumer retain integration.

The scripts are byte-identical to the private validation kit. They use constructed
inputs and the existing packaged clock/recovery/worker tests; no hosted replay,
raw trajectory, private observation, or scratch optimizer is published here.

## Run

Use the exact extracted baseline and evaluation-copy directories produced by the
private kit's `setup_workspace.py`. That setup retains all original source bytes
and makes a separate evaluation copy; never point an output at the canonical tree.

```sh
python -B test_scheduler_timeline.py --baseline /path/to/inputs/current \
  --candidate /path/to/existing-core --existing-core --report /tmp/score-tests.json
python -B run_existing_regressions.py --runtime /path/to/existing-core \
  --report /tmp/recovery-tests.json
```

The baseline scorer is deliberately pinned to SHA256
`32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`.
The tested core is
`63198d3b642847a02fee8f3553b9983341b4931b4975013209ad10777b5d1199`.
The historical filename `test_scheduler_timeline.py` is preserved. The documented
`--existing-core` mode consumes packaged code, not the private prototype.

## Recorded execution and scope

The retained run passed 11 focused methods (1,800 direct-score cases and 96
complete optimizer comparisons) plus 15 existing clock/recovery/worker methods.
Publication smoke on September 8, 2026 passed the same 26 methods from these
relocated, unchanged scripts: 0 failures/errors/skips, 0 new full games.

The separate retained 36-trial observation benchmark exercised archive
`0a47069838fb2ac5f3872b697fabf5b1bf74aff54a0bb154af2c2813b477cacb`,
not the later whole `820ed99e` package. It measured score-only reuse, not combined
compact-history, clone, or later scoped-cache effects. No benchmark was rerun for
publication; no hosted timing, cold-start repair, or gameplay improvement is claimed.

Private reproduction kit: 6,606,336 bytes, SHA256
`bc5651c9df075f7cbc3db06c0bbdbb700f6d3774023defe943554dd27f30e952`.
The owner-project Library holds exact inputs, source, raw traces and prior results.

Prior delivery: https://github.com/woahwhattheheck/commons/pull/10518#issuecomment-5584491927

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
