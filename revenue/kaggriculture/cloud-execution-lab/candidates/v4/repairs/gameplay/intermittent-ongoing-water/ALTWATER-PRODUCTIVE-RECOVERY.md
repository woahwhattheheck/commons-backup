# ALTWATER productive recovery successor

Status: **SOURCE-BOUND RESEARCH ADMISSION / DEFAULT-OFF / NO LIVE SCHEDULER PROMISE**.

This is the corrected descendant of the Gemini/Antigravity intermittent-watering idea already carried by HYDRA. It stays inside the canonical `repairs/gameplay/intermittent-ongoing-water/` owner and does not create a second watering controller.

## Why the literal rewrite is blocked

`ongoing_water_skip.py` proves a narrow engine theorem: an established TOMATO/STRAWBERRY plant at `consecutive_unwatered == 0` can survive one missed EOD, subject to the existing planting-day and fertilizer-bonus exclusions. Its original candidate transform turns that WATER row into PASS.

The convergence atlas correctly marks a bare final-action `WATER -> PASS` rewrite as safety-blocked: saving one unit action is not useful unless the row is converted into productive work, and the plant becomes a hard next-day WATER obligation after the skipped EOD.

## Corrected best form in this package

`water_harvest_recovery.py` certifies only a concrete two-day pair already present in an open-loop/replay trace:

1. the current WATER is HYDRA-eligible;
2. the same plant has positive stored `yield_units`, so `["HARVEST"]` is productive at that site under the official engine;
3. the next supplied observation is the next calendar day and shows the same crop/planted-day identity alive with `consecutive_unwatered == 1` and not yet watered;
4. the supplied next-day action contains exactly one semantic WATER actor at that site (`row[0] == "WATER"`; trailing tokens do not hide another engine-live WATER);
5. no actor at that same site executes semantic DIG in the recovery callback, so actor order cannot remove the plant before WATER or destroy it after WATER;
6. both observations are executable callbacks (`step <= 718` for the standard 720-step episode); step 719 is not accepted as recovery evidence.

Only when all six are true may the research candidate replace the current WATER row with HARVEST. The next-day action is evidence, not edited state. Missing/ambiguous recovery, duplicate semantic WATER, same-site destructive DIG, terminal step 719, zero stored yield, identity drift, weed transition, wrong day, fertilizer-bonus exposure, malformed action shape, or any existing HYDRA blocker leaves the current action unchanged.

This is deliberately narrower than a generic "find some useful action" scheduler. It converts the blocked PASS into one source-provable productive operation without inventing route/movement feasibility.

## What this does *not* claim

- No live policy or scheduler can promise the future recovery action from this certificate.
- No economics or promotion result is implied.
- No WATER suppression occurs without a materialized next-day observation/action pair.
- No PLANT, movement, market, config, runtime, COMPOSITION, archive, or Kaggle surface is changed.

## Next gate

Use current-native/replay traces to census HYDRA-eligible WATER rows that also carry stored yield, then ask how often the native next-day route already returns exactly one non-destructive semantic WATER callback to that site. Only after both-seat paired economics and zero plant-loss regressions should the shared sticky-obligation scheduler owner consider turning the two-day certificate into an obligation-aware live proposal.
