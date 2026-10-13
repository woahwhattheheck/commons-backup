# Lean20: measured continuation of the device-team farm manager

The runnable `main.py` is the exact **lean20** selection from
[study run 34085597847](https://github.com/woahwhattheheck/commons/actions/runs/34085597847).
It changes only three policy settings in Euler's frozen 28-animal/10-hand agent:
20 animals, eight hands, and no land expansion. All other executable logic is
preserved. It is a separate candidate, not an overwrite of the accepted agent or
of root's existing Kaggle submission.

## Source-specific inputs

The local-device team's published code and
[economic analysis](https://github.com/woahwhattheheck/commons/blob/c57fc2962d7a0da5109162f0b6a267967c3a616e/revenue/kaggriculture/20260907-offline-agent/ECONOMICS.md)
identified marginal land, labor and travel as useful hypotheses, while retaining
unsuccessful lifetime-economics, long-horizon and same-tile experiments. We read
those actual source files and used their successful 28/10 policy as the base.
This was reuse of the device team's published work; no physical-device files
were read or modified by this cloud build.

Base source: `c57fc2962d7a0da5109162f0b6a267967c3a616e`,
`revenue/kaggriculture/20260907-offline-agent/main.py`.
Base SHA-256: `acf541d46ceb2002caf0a3bba834109a92b755fb36afa4bda9e3d966665550ac`.
The original incumbent and compact22 opponent are separately frozen; neither
follows moving main. The official interpreter remains pinned at
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

## Development selection, before validation

Eight candidate definitions and the selection rule were committed before the
run. Each used seeds 733, 2801 and 8191, both seats, against both fixed rivals.
All 96 games completed. Means below are candidate minus opponent final coins;
these are game balances, not money earned.

| Candidate | Mean vs Euler28 | Mean vs frozen compact22 |
|---|---:|---:|
| compact22 | +1,484.667 | 0.000 |
| lean20 | **+4,667.000** | **+1,898.500** |
| dense24, no crops | -9,482.333 | -7,067.167 |
| lean22, three-crop cap | -643.500 | -3,473.000 |
| compact care-headroom | -2,875.667 | +478.833 |
| lean care-headroom | -1,432.500 | -3,590.333 |
| dense care-headroom | -13,140.000 | -8,126.333 |
| travel22 | -749.333 | +1,801.500 |

Selection maximizes the smaller of the two opponent mean margins, breaking
ties by overall mean then candidate name. **Lean20** won all 12 development
games and was selected. Neither the new care condition nor travel coefficient
is in the shipped standalone. Their behavior tests and unsuccessful results
remain reproducible in the study instead of being hidden or promoted.

## Reserved validation

Only the exact selected bytes advanced to seeds 1237, 4421, 10007, 32771, 65539,
131071, 262147 and 524287, both positions. These seeds were declared separately
and were not used for candidate selection. All 64 games completed without agent
or engine failures, with 719 action rounds per game. Replaying the first seed
against each of four opponents reproduced its exact score and trajectory hash.

| Fixed opponent | Wins / losses | Mean coin margin | Worst margin | Descriptive seed-paired 95% bootstrap interval |
|---|---:|---:|---:|---:|
| Euler28 | **15 / 1** | **+3,202.125** | -48 | +2,200.563 to +4,102.063 |
| Compact22 | **15 / 1** | **+2,713.000** | -1,263 | +2,049.438 to +3,412.750 |
| Original incumbent36 | 16 / 0 | +8,478.875 | +6,152 | +7,205.500 to +9,957.250 |
| Official starter | 16 / 0 | +94,140.375 | +41,184 | +75,544.500 to +108,433.938 |

Both losses occurred at seed 4421, candidate seat 1: 45,485 versus Euler28's
45,533; 64,471 versus compact22's 65,734. They remain in the evidence. There
was no retuning after viewing validation. Eight seed pairs and four fixed
opponents do not establish universal dominance or future leaderboard rank;
the bootstrap is descriptive, not a multiple-selection-corrected guarantee.

The first validation run measured maximum candidate decision time 1.598 ms,
maximum parent RPC 2.273 ms, and peak worker RSS 30,608 KiB including startup.
The container limited the whole evaluation to 1.6 CPU and 6.5 GiB, with networking
disabled and read-only repository source. These are observed development
measurements, not guaranteed hosted performance. The explicit interpreter driver
uses a stricter one-second RPC deadline rather than Kaggle's overage-time bank.

## Economics diagnostics without changing the game

`diagnostics.py` records requested operations and post-refresh economy snapshots
around the unchanged interpreter. It does not treat requested trades as proven
executions. Eight full games (first validation seed, both seats, all four rivals)
matched the original scores and complete action/final-state hashes exactly.
Those repetitions establish instrumentation equivalence, not eight new holdouts.

On seed 1237 versus Euler28, lean20 requested 2,943 versus 3,434 moves in seat 0
and 2,911 versus 3,370 in seat 1. It peaked at eight workers rather than nine,
and retained one land quadrant instead of buying a second. This supports the
team's labor/travel hypothesis; the simultaneous policy changes do not isolate
each mechanism's causal contribution. Full herd, inventory, price and care
backlog snapshots remain in `diagnostics.json`.

## Reproduction and preservation

Selected standalone SHA-256:
`d9487c031b50ede06a706acc8bcb40e0b5a681d9b5e92c1a1a96492b26c2dd62`.
It contains no live-source imports, external model calls, network access, or
seed-specific branches. AST tests verify that only the POLICY assignment differs
from the published base implementation. The executable study, journal recovery,
behavior regressions and actual-interpreter checks accompany the candidate.

[Original evidence artifact 10005185636](https://github.com/woahwhattheheck/commons/actions/runs/34085597847/artifacts/10005185636)
contains source snapshots, all candidate bytes, all games, selection, hashes,
runtime image and the 35 initial passing tests. Its downloaded ZIP SHA-256 is
`e7ae91b21802588c4aaf667ebe6970df9303e62e2dd827876522328ee5a044b9`.
The seven subsequent source/behavior/observer tests passed against the same
real engine in ephemeral cloud storage. The final delivery workflow also runs
those tests, checks the committed standalone against the selected artifact,
and exports the diagnostic replays. CI repetitions are not new independent data.

Code is a **candidate delivery**, not a new competition submission or payout.
The existing accepted notebook and root's submission ownership are preserved.
The owner-authored code keeps the device team's **MIT OR CC-BY-4.0** license.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
