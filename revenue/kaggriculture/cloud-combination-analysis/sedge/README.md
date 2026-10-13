# SEDGE: distinguish recorded draw counters from realized events

## Decision for the current TITAN comparison

Keep the completed conserved-versus-frozen-SELL positive cell in total-policy
performance. Its `path_divergent_days=2` is not, by itself, evidence of a different
town. Preserve the diagnostic, but label what actually changed.

This does **not** promote the conserved arm or the new ordered candidate.
The published eight-cell cross-check has seven negative own-cash deltas and one
positive, and both arms are 8/0/0. All eight deltas average **-342.375** own cash;
the seven unflagged rows average **-546.5714285714**. These are different descriptive
subsets, not alternative unbiased estimates. Do not select one subset after
seeing its favorable or unfavorable result. No aggregate margin is inferred from
the published own-cash-only table.

The new `integrated_main.py` at source `843f6dbb7d564204802d54e1611fe912aea497df`
is a **different policy** from the conserved arm below. Its existing comparison
must retain its same-producer `integrated_parent.py` control and the separately
labeled frozen SELL incumbent. Claude's completed 2x2 isolates seed recovery and
committed envelopes over that experiment's own parent; it is not a measurement
of the new ordered candidate's advantage over frozen SELL. No existing source,
running panel, development reservation or held sample is changed here.

## Exact retained discriminator

Source: `cloud-model-lab/results/t08-selected-vs-public-bank.json`, Git blob
`89115eaaebb3f1b7bb360a8370d80b82488f4165`, read at `fd9550f7`.
Cell: development seed **9890040**, own seat **1**, opponent **COK**.

| Recorded quantity | Frozen SELL | Conserved composition | Difference |
|---|---:|---:|---:|
| Final own cash | 87,890 | 88,977 | +1,087 |
| Final rival cash | 53,013 | 53,097 | +84 |
| Final margin | 34,877 | 35,880 | +1,003 |
| Result | win | win | no outcome flip |
| Day 27 total draw count | 16 | 14 | -2 |
| Day 28 total draw count | 74 | 72 | -2 |

On **both flagged days**, both arms record **no shop unlock** and **zero weeds
spawned in either farm**. The draw-count differences are the rival farm's empty
tile counts: 12 versus 10 on day 27, and 36 versus 34 on day 28. These records do
not establish a changed stochastic event on those days. They also do not identify
the economic cause of the cash delta.

The official engine at `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c` makes a fresh
`random.Random((seed * 1_000_003) ^ day)` inside `_end_of_day`. `_spawn_weeds`
consumes a draw only for an empty tile, and the shop choice follows those draws
when a shop can unlock. Therefore action-dependent occupancy can change a draw
counter. This is not equivalent to a changed shop or weed event; RNG state is
also not carried from one day to the next. See official source lines 836-889.

Do not reverse this distinction into a stronger assertion: matching counts do
**not** prove matching spatial weed coordinates, full farm states or complete
RNG streams. The current log does not record those. A real event-divergent pair
still belongs in total-policy performance; event-stratified results are useful
mechanism diagnostics, not a replacement for that total.

## Use the existing output; do not replay games

From this directory:

```sh
python -B compare_recorded.py retained_case.json --output retained_analysis.json
python -B -m unittest -v test_compare_recorded.py
```

For an already completed executor output:

```sh
python -B compare_recorded.py /path/to/t08-selected-vs-public-bank.json \
  --output /path/to/recorded-comparison.json
```

For another two-arm `rows` file, select its existing labels with `--control` and
`--candidate`. Rows must supply seed, seat, opponent, arm, own_cash and rival_cash.
Existing `path`, `margin`, `rounds`, `opponent_id`, `error` and source metadata are
consumed when present. An absent path remains unknown; a missing counterpart is
not zero-filled. Failed cells are reported separately, not counted as wins. The
CLI returns nonzero for missing/failed cells or an empty comparison. Different
opponent launcher hashes, round counts, duplicate keys and malformed records
are rejected. Matching launcher hashes are **not** a verified dependency closure.

The report preserves every successful paired cell in `total_policy`, including
cells with changed logged events. It separately reports counter-only differences,
changed shop/weed-count events, missing path coverage, zero-rival controls, cash,
rival cash, margin and W/T/L transitions. It does not claim sample independence
from identical scores across seats and does not pool different policy revisions.

## Evidence scope and provenance

`retained_case.json` is an explicitly labeled **projection** of the final-cash
fields and days 27-28 from the existing raw source, not the full original file.
It retains source path, blob, entrypoint hashes and source line ranges. The
selected case is a retrospective development discriminator, not a random sample.
The analyzer output includes the input-file SHA256 and marks the trace as a
partial excerpt. The original 29-day log remains with Claude; no policy/game
output is invented, and no original raw file is replaced.

The eight-cell own-cash table and 2x2 comparison definitions were read from
`cloud-model-lab/results/SEED-X-COMMITTED-2X2.md`, blob
`82f8efe07d206b01e173742ad254a75eee4b920d`. The accompanying 2x2 summary is blob
`a2c050c749c93ec56d6d93d2af5f4dce19b03a19`. Raw opponent source hashes and launcher
hashes differ by design: the public-bank adapters invoke hash-checked underlying
sources through the official loader; a wrapper hash is not a substitute for the
raw source/loader/assignment-mode closure.

Validation executed locally: **18 post-processing regressions**, including this
retained case and clearly synthetic mutations for changed shops/weeds, negative
outcomes, failed/missing cells, duplicate keys, invalid cash and source mismatch.
No full games, seed use, engine modification, Kaggle access, new workflow or
rerun of the accepted 79 component methods occurred. TANDEM's timing utility and
all assembler/controller files remain untouched.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
