# Canonical DEFAULT vs frozen SELL paired panel

This additive lab measures the source-frozen PR10144 canonical DEFAULT directly
against its exact strongest frozen SELL control. It uses the unmodified official
Kaggriculture interpreter pinned at `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`
(package 1.32.7), both seats for every seed, and a real one-second action RPC
deadline. It is an explicit cloud-VM driver, not hosted Kaggle scoring.

The candidate input was copied without repacking from
`cloud-execution-lab/exports/titan-current.tar.gz` at merge `4f743f8e`; its
SHA-256 is `70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb`.
The embedded [canonical SOURCE manifest](source/canonical-SOURCE.json) and
[enabled config](source/TITAN-CONFIG.json) are retained verbatim. The archive
was extracted into an offline temporary directory. The control wrapper creates
`TitanAgent(Features(consumer="frozen", seed=False))`; every selected runtime
file underneath it remained byte-identical to the candidate copy. `FREEZE.json`
records the full closure before the first game.

Fresh assigned seeds were `9922013–9922028`. Slack and current-main repository
searches had no earlier claim/result for that range. Stage 1 used four seeds;
stage 2 extended the same frozen sources to all sixteen. `9922005` appears only
in a stopped activation probe because it was already consumed by PR10005; it is
not a panel result. The exact-loss replay and frozen self-play reuse `9922023`
after the panel and are explicitly diagnostic, not additional fresh evidence.

Run topology:

```text
candidate: extracted archive/main.py::agent (shipped TITAN-CONFIG)
control:   extracted archive + source/frozen_control.py::agent
engine:    official pinned three-file cache
driver:    cloud-eval/evaluate.py, separate fresh persistent processes
limits:    action RPC 1.0 s; startup 10 s; game 120 s between steps
```

`results/stage-4.json.gz` and `results/stage-12.json.gz` are losslessly compressed
raw evaluator reports.
The compressed loss trace contains every action, per-step observation digest and
bank transition for all 719 rounds. Run `python -B verify_results.py` here to
recompute the claimed result and evidence bindings without executing a game.

Excluded by design: Claude's 384 games, WIDEFIELD's public-opponent bank, T15
adaptive panels, Kaggle upload/notebook changes, and any new VM or paid service.
Arlene was not rerun: the strongest internal comparison directly answers this
incremental question, while the hosted Arlene byte identity remains conditional.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
