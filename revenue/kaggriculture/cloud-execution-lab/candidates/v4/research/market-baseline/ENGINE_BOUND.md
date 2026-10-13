# Engine-bound passive baseline donor integration

This file records the absorption of the closed-unmerged ASTRA-TOWNCURVE donor PR #12794 into the earlier and authoritative ASTRA-BASELINE package. No second baseline tree is created.

## Preserved donor surface

`engine_bound_baseline.py` is the donor's exact source blob `7d0b5d43c981190eba61d65f65348bb4688f2b91`. It pins official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`, imports that engine, constructs two real passive farms, then calls official `_town_consume` and `_end_of_day`. This preserves the daily RNG call order in which player-0 weed draws and player-1 weed draws occur before replacement-shop `rng.choice`.

The runner also provides an exact passive envelope over every legal shop-identity sequence and `classify()`, a diagnostic that labels public market inventory as within/below/above that envelope and never emits actions.

`test_engine_bound_baseline.py` ports the donor's focused tests into this package and fixes the integration path: from `candidates/v4/research/market-baseline/`, `cloud-execution-lab` is `HERE.parents[3]`, not `HERE.parents[4]`. The original closed donor carrier remains unmerged.

## Step-index correction

The already-landed reduced `market_baseline.py` applies town/shop consumption for action callback `s` and records the resulting post-consume market state in its row `step=s`. The official interpreter exposes that resulting market state on the next observation, `s+1`.

Therefore the reduced aggregate's legacy `first_step_*` fields are **causing consumption-action steps**, not first-visible observation steps. `VISIBLE_STEPS.json` makes the relation machine-readable (`visible = action + 1`). The key requested sentinels are:

* STRAWBERRY: action 260/348/680 -> visible 261/349/681 (min/median/max), 97/100 seeds.
* WOOL: action 200/388/656 -> visible 201/389/657, 55/100 seeds.

The final reduced row after action 718 corresponds to terminal visible observation 719.

## Evidence boundary

The reduced model was executed locally (7/7 in the first merged packet; an additional local semantic check reproduced the visible-step sentinels before this donor absorption). The engine-bound donor source and its expected receipt came from #12794, but this follow-up does **not** claim a new local full-engine execution because the authoring runtime does not contain the repository checkout / `kaggle_environments` package. The ported engine-bound test is intended to run where the pinned repository engine file is present; its loader includes the donor's minimal `kaggle_environments.utils` shim and fails closed on engine-byte drift.

No gameplay policy, controller, runtime key, default, archive, workflow, or Kaggle submission is changed here.
