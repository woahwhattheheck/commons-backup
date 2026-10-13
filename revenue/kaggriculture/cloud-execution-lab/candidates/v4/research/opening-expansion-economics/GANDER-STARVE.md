# GANDER × STARVEORACLE — alternating-feed goose service

This package strengthens two corrected Gemini ideas inside the single existing V4 opening-expansion authority. It is research evidence, not a new controller or default.

## Composite result

Canonical GANDER certifies a feasible Day-0 frontier of **9 GOOSE + one HIRE**. Those geese are placed before EOD0 and become fertilizer-ready, but they also finish that refresh with `consecutive_unfed = 1` because they were not fed on placement day.

That detail changes the naive starvation story: **Day 1 cannot be skipped.** A second miss at EOD1 would make every goose escape. The other endpoint matters too: the official interpreter marks the episode DONE at callback **718 = episodeSteps - 2** for the reviewed `episodeSteps = 720` specification, so Day 29 hour 23 / step 719 and the Day-29 EOD refresh never execute. Feeding on Day 29 therefore cannot prevent any later starvation event; it is terminal dead work.

The safe source-bound cadence is:

- Day 1: FEED + COLLECT_FERTILIZER all nine geese.
- Day 2: skip FEED; collect FERTILIZER.
- Day 3: FEED + collect FERTILIZER.
- Day 4: skip FEED; collect FERTILIZER and HARVEST EGG.
- Continue FEED on odd days through **Day 27** and skip on even days through Day 28.
- **Day 29:** skip FEED, collect the fertilizer made at EOD28, harvest the EGG made at EOD28, and stop at callback 718. There is no EOD29 refresh to service.

The exact-interpreter composite uses GANDER's two-worker site partition and one fresh HIRE per service day. On mature skip-feed days, the nine freed FEED actions are spent on nine HARVEST actions while fertilizer collection remains daily. CARE is never used.

Across the real Day 1..29 callback window, the constructed cadence is expected to:

- feed on **14 days** and skip on 15, with the final feed on Day 27;
- consume **126 WHEAT**;
- save **126 WHEAT units and 126 FEED attempts** versus feeding all nine every day through the last real EOD (Days 1..28 = 252 feed units);
- preserve all 9 geese with maximum observed unfed streak 1;
- realize all **234 base EGG = 9 × 26** produced by the real EOD3..EOD28 refreshes;
- realize all **261 FERTILIZER = 9 × 29** available from EOD0 plus EOD1..EOD28;
- finish with zero held EGG and zero pending fertilizer after the terminal Day-29 extraction;
- keep observed per-goose held EGG at at most 2, below the engine `max_held = 4`;
- stop on exact callback 718 with both interpreter states `DONE`, rather than inventing a step-719 refresh.

These are mechanism/action/WHEAT-unit expectations until the repo-mounted executor returns an exact receipt. They are **not cash or terminal-margin results**: WHEAT acquisition price, EGG/FERT sale timing, shed pressure, CARE opportunity cost, rival behavior, town demand and displaced opening work are not priced here.

## Route-capacity dividend

The alternation is more than a WHEAT discount. Under the exact canonical GANDER two-worker partition:

| service | main farmer | hired hand | regular 23 slots | terminal 22 slots |
| --- | ---: | ---: | --- | --- |
| FEED + FERT | 20 | 21 | fits | fits |
| skip FEED + FERT + HARVEST | 19 | 20 | fits | **fits** |
| FEED + FERT + HARVEST | 25 | 25 | **does not fit** | **does not fit** |

So an all-nine same-day full service pass cannot be performed by these two workers when FEED is retained. Removing FEED on the safe alternating days makes the all-nine EGG harvest fit while still collecting every FERT, and the 19/20 terminal extraction route still fits the shorter Day-29 window after the HIRE. This does not prove that no more complex rotating-harvest schedule could work under daily feeding; it proves the direct full-service route that the composite replaces is infeasible and quantifies the capacity created by the skip.

## Why this is stronger than either input alone

STARVEORACLE proves that an unfed-but-surviving goose still receives base EGG production and fertilizer, but it does not prove a nine-goose live route can service the next feed and realize output in time. GANDER proves the nine-goose geometry and daily FEED/FERT route, but it pays the full WHEAT/action load.

The composite closes that gap. GANDER supplies the route and post-EOD0 state; STARVEORACLE supplies the one-miss production theorem; the freed feed slot supplies the missing EGG collection capacity on skip days; and the official `episodeSteps - 2` boundary removes the final useless feed entirely. The resulting cadence satisfies starvation admission mechanically while remaining explicit about CARE and economics.

## Predecessor killers

`gander_starve_cadence.py` executes the historical naive phase that skips Day 1. Because EOD0 already created the first unfed strike, all geese escape at EOD1. The focused tests also require the **official interpreter itself** to transition both seats to `DONE` at callback 718 and forbid a synthetic EOD29. Those boundaries prevent future refactors from resurrecting either bad literal rule: “start by skipping” or “feed the terminal day.”

## Source custody

The composite captures every executable authority file **once**, authenticates those captured bytes, and then executes those exact same byte snapshots. It never authenticates one pathname read and later reopens the mutable pathname for execution:

- official engine Python Git blob `3c202c7ee921da239356789e266b694635103fc4`;
- official engine Python SHA-256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`;
- adjacent official `kaggriculture.json` Git blob `b354d06b742fe48402513792253f1a5c29366b20`;
- adjacent official `kaggriculture.json` SHA-256 `a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867`, exactly 6,002 bytes;
- GANDER helper `goose_printer_oracle.py` Git blob `38ae7715c233c74f24aacd5fe09f4d0d7a630037`;
- STARVEORACLE helper `starvation_cadence.py` Git blob `8831ff953faf033cc6d3892c6f32ccd1ee1af06c`.

The GANDER helper, STARVEORACLE helper, official engine Python and adjacent engine specification are all captured before execution. The engine's module-level `open(kaggriculture.json)` is intercepted and served from the already-authenticated JSON byte snapshot, following the proven SHOPSTREAM custody pattern. Reported source identities are derived from those same snapshots.

A focused swap-after-capture regression replaces **all four** backing authority pathnames—GANDER helper, STARVE helper, engine Python and engine JSON—with poison immediately after their one allowed byte read. The authenticated snapshots must still execute, the engine must expose the reviewed `kaggriculture` specification with `episodeSteps = 720`, and any second authority-path byte read is a hard test failure.

GANDER supplies site geometry and authored Day-1 route counts; STARVEORACLE supplies state/environment construction and intermittent-feed semantics. The simulator overrides STARVEORACLE's intentionally huge generic probe horizon with the reviewed official `episodeSteps = 720`, then runs the captured official interpreter from Day 1 through callback 718 only.

## Next gate

The gameplay/economics owner should consume this cadence through the existing opener/native scheduler, not a sibling controller. Run current-native both seats against current opponents and compare the incumbent opening with feasible GANDER counts under exact WHEAT acquisition and sale behavior. Record CARE displacement, shed occupancy, EGG/FERT realization and sale timing, fallback feed-deadline safety, terminal-day extraction, natural engagement, and terminal margin.

Promotion requires positive paired terminal economics with no escape/storage/new-loss regressions. The 126-unit WHEAT saving, two-worker route-capacity dividend, and terminal dead-feed deletion are strong mechanism signals, not an activation decision.

## Validation

From this directory:

```bash
python test_gander_starve_cadence.py
python -O test_gander_starve_cadence.py
python -m py_compile gander_starve_cadence.py test_gander_starve_cadence.py
python gander_starve_cadence.py
```

The focused suite exercises the exact interpreter, mandatory Day-1 feed predecessor, official step-718 terminal boundary, full nine-goose survival/output, held-cap safety, regular/terminal route fit and full-service overflow, immutable helper/engine/metadata source custody with swap-after-capture killers, explicit CARE exclusion and exact source identities.
