# CROPSCALE — source-derived crop service capacity

This package is a **V4 research/admission primitive**, not another crop policy, router, scheduler, or controller.

## Why this exists

Historical merged PR **#9806 (FLORA)** replaced a fixed crop cap with a worker/service-load bound and reported a +$5,315.75 mean improvement against its shipped checkpoint on two paired development seeds. That donor used policy allowances (`0.52`, `3.2`, `1.45`) rather than engine constants, so CROPSCALE does **not** transplant its formula.

The current official engine blob `3c202c7ee921da239356789e266b694635103fc4` provides a harder theorem:

1. `PLANT` calls `_new_plant(...)`.
2. `_new_plant` initializes `consecutive_unwatered = 1` and `watered_today = False`.
3. At end of day, an unwatered plant increments `consecutive_unwatered`.
4. At `>= 2`, the plant becomes a weed.

So a new crop site that still exists after a same-day EOD needs at least **two unit actions before that boundary: PLANT + WATER**. The terminal horizon matters: if the episode ends before that EOD executes, the weed transition never happens and the hard action-budget lower bound is only the PLANT action. Movement, seed collateral, fertilizer, harvest, animal service, shed work, and every other action only consume additional capacity.

## Land-bound correction

The first CROPSCALE revision capped both impossibility ceilings by **currently empty owned tiles**. That is not one-sided safe. In the same official engine, `_process_market` executes `BUY_LAND` atomically after the callback's unit actions, and `_do_buy_land` immediately converts the next locked quadrant's `LOCKED` cells to `None`. Those cells are therefore available to later same-day callbacks. `DIG` and some `HARVEST` actions can also reclaim occupied cells.

`empty_owned_tiles` remains useful telemetry, but it is **not a hard future physical cap** unless a caller separately proves no land acquisition or tile reclamation. CROPSCALE now caps its impossibility envelopes by the total rectangular board cell count observed in `farm["tiles"]`. That is deliberately generous: it may credit locked or occupied cells whose cash/action path is actually impossible. Over-credit is correct for an impossibility bound; under-credit is not.

## API

`capacity_envelope(observation, configuration=None, *, configuration_authenticated=False)` returns two ceilings:

- `current_labor_ceiling`: conditional only on taking **no future HIRE credit**. It uses farmer + currently present hands across executable callbacks remaining before the earlier of same-day EOD and terminal, and caps by total observed board cells. It does not assume the current empty-owned set is frozen.
- `absolute_action_ceiling`: a deliberately loose hard upper bound. It grants the full `maxMarketOrdersPerTurn` as successful HIRE rows after every executable remaining callback, gives every new hand every later unit-action slot, ignores cash and all competing market/LAND work, and caps only by total observed board cells.

The envelope also reports `step`, `episode_steps`, `callbacks_remaining`, `eod_reachable_before_terminal`, `unit_actions_per_surviving_new_plant`, `empty_owned_tiles`, and `board_tiles` so downstream planners can see exactly which one-sided theorem produced the ceiling.

Terminal handling is part of the proof. The pinned official engine makes `episodeSteps - 2` the final executable callback. CROPSCALE therefore binds observation `hour` to `step % turnsPerDay`, refuses observations after that final callback, and caps callback credit at the terminal horizon. If the same day's hour-23 EOD callback is reachable, each surviving new plant is charged two unit actions. If terminal arrives first, it is charged only one PLANT action because no same-day weed transition can execute. Under the standard `episodeSteps=720` / `turnsPerDay=24` defaults, step696/hour0 has 23 executable callbacks through step718 but no hour-23 EOD; one actor therefore has a 23-plant action-count ceiling, not the stale 12-plant PLANT+WATER ceiling.

`assess_proposed_expansion(...)` returns only:
- `IMPOSSIBLE_ACTION_BUDGET`, or
- `NOT_CERTIFIED`.

It never returns SAFE. Passing the action-count bound does not prove movement, seed availability, target assignment, land acquisition, tile reclamation, watering route, market execution, or economic value.

Configuration is part of this one-sided proof. Omitting `configuration` uses the pinned official defaults from configuration blob `b354d06b742fe48402513792253f1a5c29366b20`. Any explicit configuration map can change `turnsPerDay`, `episodeSteps`, or `maxMarketOrdersPerTurn` and therefore the computed impossibility ceiling, so it is rejected unless the caller has bound those values to the interpreter instance and sets `configuration_authenticated=True` literally. Direct `capacity_envelope(...)` use raises `CapacityInputError("configuration_not_authenticated")`; `assess_proposed_expansion(...)` fails closed as `NOT_CERTIFIED` with no trusted ceiling or envelope. Authenticated overrides remain caller-custodied rather than being falsely attributed to the default configuration blob.

## PLANTGUARD — authenticated same-EOD survival

Gemini/Antigravity's PLANTGUARD observation is stronger than a generic action-count warning: a current PLANT can be rejected when the **actual authored unit suffix** proves that a plant which still exists at EOD receives no WATER after creation and before that EOD.

`plant_guard.py` adds that one-sided certificate inside this same CROPSCALE authority. `assess_same_eod_plant_survival(...)` consumes the current selected action plus exactly one authenticated action dict for every remaining executable callback before that same EOD. It never predicts or invents a route.

The verifier accounts for the mechanics that make the raw slogan unsafe to apply directly:

- only a current PLANT that can actually be certified as creating a crop is considered: the tile must initially be empty, the crop must be known, same-crop aggregate seed demand must not exceed private seed custody, and only the first executable colocated PLANT can own a target;
- current unit rows execute farmer then hands: an earlier same-site `BUILD_COOP` or `BUILD_PASTURE` can occupy an initially empty tile before a later PLANT, so unresolved build success returns `NOT_CERTIFIED` rather than falsely labeling that later PLANT doomed; earlier DIG/HARVEST reclamation of an initially occupied tile remains conservative and is not promoted into a candidate;
- same-callback actor order is exact: WATER by an actor **before** the PLANT does not help; WATER by a later actor on the same tile does;
- `DIG` is also actor-ordered custody, not merely a route action: the pinned engine removes plants with DIG. A same-site DIG after the certified PLANT removes that candidate, so it cannot support a same-EOD weed-doom certificate; a DIG before a later PLANT on an initially empty tile is a no-op. Later authored callbacks apply the same rule. Mixed results can still doom surviving unwatered candidates while reporting removed candidates separately;
- actor positions are carried through NORTH/SOUTH/EAST/WEST commands, including out-of-bounds movement no-ops, so later WATER or DIG must physically occur on the candidate tile;
- observation `hour` is strict-integer bound to `step % turnsPerDay`; a caller-inconsistent or type-poisoned clock cannot mint an EOD certificate;
- terminal horizon is part of the proof: the pinned official engine blob `3c202c7ee921da239356789e266b694635103fc4` marks the callback at `episodeSteps - 2` as the last executable callback. The pinned official configuration blob `b354d06b742fe48402513792253f1a5c29366b20` supplies the standard `episodeSteps=720` and `turnsPerDay=24` defaults. PLANTGUARD therefore proves that this day's hour-23/EOD callback lies at or before that boundary. Under those standard defaults, step718/hour22 cannot be rejected using a nominal authored step719 because step719 and that EOD never execute; the last real EOD callback is step695/hour23;
- omitted `configuration` uses those pinned official defaults. Any explicit configuration map is proof-critical and is rejected unless `configuration_authenticated=True` literally; callers may set that flag only after binding the supplied `episodeSteps`, `turnsPerDay`, and related values to the exact interpreter instance whose authored actions are being evaluated;
- returned evidence names both `engine_git_blob` and `configuration_git_blob`, and resolved reports expose `removed_actor_indices` alongside watered/doomed actors. The configuration blob identifies the source of the **default** values; authenticated explicit overrides remain caller-custodied rather than being falsely attributed to that blob;
- the suffix must be complete through a **reachable** EOD and preserve existing actor cardinality;
- an executable HIRE before the final callback destroys one-sided rejection because a new actor could create an unrepresented watering path; HIRE beyond the market row cap is inert, and a final-hour HIRE cannot act before that EOD;
- malformed, incomplete, terminal-unreachable, type-poisoned, suffix-unauthenticated, configuration-unauthenticated, or actor-ambiguous evidence returns `NOT_CERTIFIED`.

The only rejection verdict is `DOOMED_AUTHORED_SUFFIX`. A found WATER or removal of every candidate returns `NOT_CERTIFIED`, **not SAFE**. The helper changes no action itself and has no runtime/default/config authority. A scheduler may consume the certificate only after proving custody of the authored suffix; omitted configuration is bound to the pinned official defaults, while any explicit custom configuration additionally requires literal `configuration_authenticated=True` after the caller proves interpreter custody. Current-native engagement and both-seat economics remain mandatory before suppressing any PLANT in production.

## Ownership boundaries

CROPSCALE does not:
- choose crop species or quantities from prices/demand;
- alter MELON/STRAWBERRY/WHEAT economics;
- claim animal acquisition/collection throughput;
- allocate workers or invent movement routes;
- credit same-callback BUY_SEED or HIRE before unit execution;
- prove BUY_LAND/DIG/HARVEST feasibility merely because the envelope over-credits their possible cells;
- treat an authored suffix or caller-supplied configuration as authenticated on its own;
- modify returned actions, config defaults, runtime, archive, or Kaggle state.

It is intended as an input to the existing single V4 planner/composition path.

## Reproduce

```bash
cd revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/crop-service-capacity
python -B test_crop_service_capacity.py
python -O -B test_crop_service_capacity.py
python -B test_plant_guard.py
python -O -B test_plant_guard.py
python -m py_compile crop_service_capacity.py test_crop_service_capacity.py plant_guard.py test_plant_guard.py
```

Expected: **27 CROPSCALE tests** and **37 PLANTGUARD tests** pass in each mode.

## Evidence limits

The historical +$5,315.75 result belongs to PR #9806's old policy and is donor evidence only. This package makes **no current-native EV claim** and activates nothing. Its contribution is replacing a stale heuristic crop-cap concept with conservative source-derived admission theorems while refusing false impossibility from a current empty-tile snapshot, an unauthenticated configuration, or a terminal partial day with no EOD; false survival claims from an unauthenticated planting route or custom configuration; false same-EOD rejection when the episode terminates before that EOD can execute; and false weed-doom claims for a plant that authored actions remove before EOD.
