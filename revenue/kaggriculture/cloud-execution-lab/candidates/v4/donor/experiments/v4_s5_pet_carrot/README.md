# TITAN V4 S5 — PET_CAFE-first carrot capacity residual

Status: **analysis only / no gameplay change / no default change**.

This lane follows S4's seed-volume census. S4 rejected the naive idea that V3.1 simply needs more seed volume; leaders actually buy slightly fewer total seeds. The remaining loss-side composition residual is much narrower: when the **first town shop is `PET_CAFE`**, leaders replace a large amount of V3.1's wheat-heavy seed mix with carrots and turn that into substantially more carrot revenue.

## Reproduction

Source data: `ledger_v31_vs_leaders.json` from the 2026-09-11 Slack bundle **Kaggriculture leaders pull v3 (adds V3.1 vs leaders)**.

```bash
python analyze_pet_carrot.py /path/to/ledger_v31_vs_leaders.json
```

The script uses only Python's standard library. Seed units are recovered from recorded seed spend using the game costs WHEAT=10, CARROT=20, TOMATO=50, STRAWBERRY=100, MELON=80.

## What survives control

Across the 180-cell ledger, V3.1 loses 83 cells. In those losses, leaders buy about **26.66 fewer WHEAT seeds** and **12.18 more CARROT seeds** than V3.1 on average.

The sharper split is first-shop `PET_CAFE`:

- 26 PET-first cells; V3.1 loses 16/26 (**61.5%**).
- Across all PET-first cells, leader-minus-V3.1 seed gaps are **-24.62 WHEAT** and **+41.27 CARROT**.
- PET-first leader-minus-V3.1 CARROT revenue gap: **+$7,402**; CARROT production gap: **+120.23 units**.
- PET-first losses alone: **+37.44 CARROT seeds**, **+$8,012 CARROT revenue**, **+121.0 CARROT units**.
- Non-PET losses: only **+6.15 CARROT seeds**, **+$1,809 CARROT revenue**, **+20.22 CARROT units**.

A same-leader control keeps only leaders with at least two PET-first and two non-PET cells. Seven leaders qualify. Averaging each leader's PET-minus-non-PET shift, PET-first moves the leader margin by **+$6,778**, the CARROT seed gap by **+32.95**, and the CARROT revenue gap by **+$5,974**. This is not merely a cross-leader style artifact.

## Negative control: reject PIZZA/TOMATO

A superficially similar PIZZA_SHOP-first / TOMATO story does **not** survive the same control. Eight leaders have at least two cells in each arm; their mean PIZZA-minus-non-PIZZA shift is **-$3,032 leader margin**, only **+1.34 TOMATO seeds**, and **-$364 TOMATO revenue**. Do not build a generic crop-mix or PIZZA/TOMATO knob from this census.

## Candidate policy experiment

If source inspection proves there is an occupancy-safe substitution seam, test only:

- trigger: **first shop is `PET_CAFE`**;
- quantities: `q ∈ {16, 24, 32}`;
- action: replace `q` WHEAT seed buys with `q` CARROT seed buys **and replace the matched WHEAT planting actions with CARROT planting actions**;
- do not add market rows, actions, tiles, land, hands, or seed volume;
- incremental seed budget is `+$10 × q` = **+$160 / +$240 / +$320** versus WHEAT;
- ship any implementation behind a new key that defaults **OFF** and fails closed when cash, seed availability, or a matched planting slot is unavailable.

### RNG / occupancy hard invariant

Seed-count preservation is **not enough** for Kaggriculture RNG neutrality. Crop maturity changes can change later farm occupancy, and empty farm tiles consume RNG before shop draws on shop nights. Therefore every candidate must be compared to exact V4 head and hard-rejected if it changes either:

1. shop-night empty-tile count / occupancy trajectory, or
2. realized shop sequence.

If an implementation cannot preserve those invariants, this lane is **NO-BUILD** rather than a speculative score knob.

## Gate

This artifact intentionally stops before policy code. A follow-up implementation is justified only after a source-level seam can guarantee matched seed/plant substitution and expose the occupancy/shop-sequence invariants to a focused test. Then run the standard V4 paired gate against the exact current `titan/v4-20260911` head. No default-on promotion without a genuine paired win.
