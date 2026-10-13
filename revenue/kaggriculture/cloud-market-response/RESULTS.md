# T12 results — no policy promotion

All primary games used the pinned official engine in the cloud, 719 decisions
per game, with both seats and the same seed/opponent paired across arms. Counts
below are local experiments, not hosted Kaggle matches or rating changes.

| Panel | Games | Intact Arlene W/T/L | Frozen SELL W/T/L | T12 response W/T/L | Response minus SELL |
|---|---:|---:|---:|---:|---|
| v1 development | 12 | 2/2/0 | 4/0/0 | 4/0/0 | Two −70 and two −132 margin losses |
| v2 intact development | 36 | 6/6/0 | 12/0/0 | 12/0/0 | Ten unchanged, two −4 |
| v2 stress development | 54 | 18/0/0 | 18/0/0 | 18/0/0 | All 18 unchanged |
| v2 held | 60 | 16/4/0 | 20/0/0 | 20/0/0 | All 20 unchanged |

v2 development used 9840001/9840019/9840037. Held used 9840101/9840119
with a locally saved pre-run source freeze. The stress opponents are FLOW's
unchanged sale-cadence, crop-demand and labor-cadence transformations, not
presumed stronger agents. No T09 evaluation seeds were used.

## Forecasting and decisions are different tests

Held-window prediction metrics below use only the frozen SELL control's
observations. Forecasts were saved before the nine-turn outcome and scored
against evaluation-only actual rival sales after completion. These overlapping
windows and repeated seats are correlated; empirical ranges are not calibrated
confidence intervals or probabilities.

| Held opponent | Forecast absolute error | Zero-supply absolute error | Relative change |
|---|---:|---:|---:|
| Intact Arlene | 22,816 | 26,874 | 15.1% lower |
| Intact Apex | 19,724 | 22,428 | 12.1% lower |
| Apex crop-demand stress | 21,124 | 21,182 | 0.27% lower |
| Arlene sale-cadence stress | 6,960 | 6,552 | 6.23% higher |
| Arlene labor-cadence stress | 0 | 0 | Uninformative; no error to improve |

The first hourly-median treatment erased shifted sale batches and lost margin.
v2 keeps entire causal historical windows, stock-bounded scenarios and the
existing seller's standing rival cases. It improved this forecast metric on
two intact opponents but did not establish improved game play. The 20 held
response/control pairs are action-for-action identical across all 14,380
candidate decisions. The unchanged selected SELL remains the default.

The intact development panel contains eight selected response plans and eight
actual changed actions. The stress development panel contains two selected
plans but zero changed actions: selection of a future plan is not automatically
a change to the current action. Held has neither selected nor changed actions.
Only two held environment seeds were tested; there is no broad-generalization
or independent-20-seed claim.

## Validation and preserved failures

* 16 regression tests passed, including causal cutoffs, censoring, shifted
  windows, single-shed stock bounds, complete inventory and paired receipts.
* 168 actual official market cases passed: seven non-operating products,
  four inventory/floor regimes, three order alignments and duplicate queues.
* All 150 v2 games completed, with 753,900 product interval checks containing
  the evaluation-only actual rival sales. Floor intervals can be broad; coverage
  alone does not establish predictive precision.
* Four process-isolated full-game development replications used the pinned
  official raw-file loader, including first-call setup under a 1 second deadline.
  All reproduce the in-process terminal scores; maximum candidate call was
  0.471052 seconds. A fifth replication from the relocated archive also matches,
  with maximum candidate call 0.179855 seconds. These are local process checks,
  not proof of hosted sandbox performance.

The initial official-file-loader attempt failed before a game because raw
execution did not define `__file__`. The separate lazy `main.py` resolves the
loader-supplied `__raw_path__` on first call. The frozen policy/model were not
changed after held evaluation. The original failure log remains in evidence.

An initial v2 selected-plan fixture omitted other inventory products and raised
KeyError during town consumption. The complete inventory correction preceded
the v2 freeze. Its failed attempts are separate from all final panel counts.
The losing v1 source, original results and changed-turn evidence are preserved.

## Evidence layout

`results/games.csv` records all 162 complete v1/v2 games, actual terminal cash
(including tied games whose engine rewards are zero), source trace hashes,
paired margin deltas, selected plans and actual changed actions.
`results/summary.json` retains all per-panel/seed/opponent comparisons and
forecast totals. `results/game-records.json.gz` stores the original result
objects, including runtime/engine hashes and timing, not only a prose summary.
`results/changed-turns.json.gz` keeps both arms' actual action/state/receipt
records for every changed response turn. `archive/v1-source.tar.gz` preserves
the earlier implementation. Official market cases, process records, failure
logs and the package source manifest are also retained.

The repository contains compact `games.csv` and `VALIDATION.json` with all
162 outcomes, paired deltas and validation counts. The complete structured
files described above, earlier source and all 719-turn traces are in the
separately delivered `t12-full-evidence.tar.gz`; they are not claimed as GitHub
source files. Every complete game record identifies its full trace SHA-256.
Neither trace truth nor result files are included in the agent package.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
