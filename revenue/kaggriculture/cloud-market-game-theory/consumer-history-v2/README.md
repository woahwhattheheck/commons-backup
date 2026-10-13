# One TITAN: packaged history ON/OFF consumer

This executes the exact PR10152 history-v2 archive through its public
`TitanAgent(Features(**history_config))` interface. It adds no policy, parent,
history model or selector. The evaluation entry toggles only `terminal_history`;
all other fields come from the archived TITAN-HISTORY-CONFIG.json. Diagnostics
are removed from the returned evaluation envelope before the official engine.

Archive:273872 bytes, SHA256
`75740d430c8d137ad4074432f47b7480df1f6864b03e84a367c7e068d27f51ba`.
Source commit `da790b74c148088be8ab7523b62f642def0711ff`, merged by PR10152 at
`2fc1418f3724ac09232e35a2a583414ce0ee8f84`.
Embedded SOURCE.json SHA256
`074ecbb52247c7ce8b537e66e4ed91c203ac91553b0c6f756aa61fbc785ae8dd`.
All71 runtime manifest entries match their sizes and hashes. Archive bytes are
consumed from the existing Git object, safely extracted into a separate cloud
runtime, and never modified or exported again. Original notices remain there.

Final sixteen-seed outcome:128/128 games, each arm62W/2L, all64 paired engine
traces and cash identical. See [RESULTS.md](RESULTS.md) and
[ACTIVATION-DIAGNOSIS.json](ACTIVATION-DIAGNOSIS.json). This is a development
ablation of one TITAN; the original integration owner retains the current
archive/default/submission path.

## First completed chunk

DEVELOPMENT9943201-9943204:32 attempts,32 complete719-action games,149.32s
panel wall. Both arms15W/1L: SELL7W/1L, COK10 8W. All16 paired engine traces,
own cash and rival cash match. Candidate seat0 vs SELL9943203 finishes with a negative margin;
both arms59067 own/59407 rival. It remains in the original record.

Every ON game records719 parent calls and718 history reconciliation turns.
Eight terminal families are ready and eight have fewer than three common historical
lags. Actual floor-censored WOOL/STRAWBERRY entries explain the exclusions;
FIRST4.json retains each lag and original interval. All8 ready families collapse
to one quiet rival queue. Native tables complete, but their absolute-win objective
already gives the baseline the optimum, so the baseline tie rule changes no queue.

Actual final rival actions can be nonquiet: SELL9943201 liquidates MILK5, WOOL2,
CARROT47, EGG2 and FERTILIZER9. Same-hour ordinary-day historical sales do not
represent that terminal liquidation. This is evaluation evidence about the
specified finite family, never a private-state or future-action input to policy.
No probability calibration or whole-game superiority is inferred.

The unchanged freeze completed through DEVELOPMENT9943216 to measure eligibility
and terminal-family mismatch across more reached observations. First4 evidence
is separately retained. These are development games, not held or hosted results.
No old T11/T12/T15 panels, WIDEFIELD9921, ECON9922 or Claude99022 cells are reused.

## Reproduction and evidence

`runtime-resolution.json` records the exact cloud paths used. Reproduction in
another runtime must first extract the pinned archive and bind its paths, the
existing official engine/evaluator, exact frozen SELL and retained licensed COK10
bank. Update path bindings in a separately named freeze; do not overwrite this
historical SOURCE-FREEZE.json. The runner checks frozen source before and after
execution. SOURCE-FREEZE.json retains full enabled configuration and dependencies.

Executed command from repository root:

```sh
python -B revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/run_panel.py --seeds 9943201,9943202,9943203,9943204 --output revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/results/first4 --jobs 2
```

Each game starts fresh actors. Existing cloud-eval supplies1s external action RPC,
120s episode wall, zero overage and existing child CPU/wall measurements. Returned
call timing includes lazy package initialization and evidence extraction; external
RPC includes serialization/transport. The driver retains full candidate inputs,
both returned actions, terminal history records and any incomplete-call input.
It never supplies rival private observations to the candidate.

Each `.json` receipt links its complete `.trace.json.gz` by SHA256. Reports retain
original per-call records, partial banks, actor timing and null scores where applicable.
`report.py` aggregates real receipts without imputing W/T/L for incomplete games.
No model/component test battery or new timing framework was substituted for games.

Own harness source is Apache-2.0. Official engine, package and public-bank sources
retain their existing licenses and exact source pins. Selected default unchanged;
no Kaggle upload, notebook write, owner-PC compute, new VM or paid execution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
