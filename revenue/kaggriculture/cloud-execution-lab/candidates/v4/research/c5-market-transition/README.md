# C5: actual-engine transition oracle and sale-timing boundary

Owner/claim: `ASTRA-C5-ORACLE / C5-PINNED-MARKET-TRANSITION-20260911-01`.
Home: the sole canonical `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/c5-market-transition/`.
This is executable research/regression evidence for the existing C5 mechanism, not another V4 tree, a new gameplay key, or a production patch.

## What was executed

On Python 3.13.5, the exact published runner and test bytes passed:

- **23/23 independent test methods under normal Python and 23/23 under `python -O`.** Four deliberately incorrect variants are detected in each mode: omitted town subtraction, omitted own-buy masking, raw-row compaction, and reversed inventory-transition sign.
- **4,263 deterministic synthetic market/town worlds, 8,526 seat checks per mode**, consisting of 167 explicit boundary worlds plus 4,096 seeded worlds. Zero observed causal, action-identity, or row-custody violations; 6,603 valid transition records; 1,923 invalid records correctly fail closed; 440 positive gross-buy lower bounds and 212 actual relocation witnesses.
- **648 matched immediate-cash timing pairs per mode**: 64 positive, 76 negative, 508 zero cash-margin changes. Both seats are included; every pair must have identical final private inventories, public market, and noncash farm state. These are not episode outcomes or population-frequency estimates. PASS rows are deliberately repeated across the raw-slot dimension, so the counts are a test grid, not a probability distribution.
- Instrumented versus uninstrumented official phase execution agrees on all state for 231 worlds. Instrumentation only forwards the original `_commit_unit` and records successful WHEAT fills; a `finally` restores the original callable.
- `py_compile` passed. Normal and optimized full-corpus JSON outputs were byte-identical.

The reviewed C5 helper is unchanged. Its existing full materialized-package suite was **not** run here; this is a new standalone engine-phase suite. No hosted CI, full games, leaderboard improvement, or feature-promotion approval is claimed.

## Exact source custody

| Input/output | Git blob |
| --- | --- |
| Official engine `kaggriculture.py` | `3c202c7ee921da239356789e266b694635103fc4` |
| Engine-adjacent `kaggriculture.json` | `b354d06b742fe48402513792253f1a5c29366b20` |
| Existing canonical donor `r04_c5_wheat_demand.py` | `d5ea1757975099409a00a32e9c7eb6d40bf51926` |
| This oracle, 20,220 bytes | `a003f2cf327cf1e1d5188746823b6bada3224cab` |
| This test suite, 14,052 bytes | `9d54223f21c60b39e2f6f5c49b05f1427c43ccc8` |
| Generated `RECEIPT.json`, 2,882 bytes | `f71e8eb1ab20725a677dbb6996eb3fe1292ef130` |

The engine/schema were extracted from existing GitHub Actions artifact `10288841962`, ZIP SHA256 `189b04ca31bc3125b6dff657d081d56ccf6c87c1ca4ab5968ab008926648aa40`, paths `seed-retry-runtime/checks/reference/engine/kaggriculture.py` and adjacent JSON. The artifact's modern selected-action runtime is **not** a compatible legacy R04 materialized package; it is not executed by this oracle.

The loader validates all three input Git-blob pins before use. It removes exactly the reviewed external `resolve_episode_seed` import from the parsed engine and replaces it with a raising guard. All engine function bodies remain unchanged. Actual `_process_market`, `_commit_unit`, pricing, parsing, and `_town_consume` functions execute. Game initialization, full interpreter lifecycle, farm unit actions, EOD, and the Kaggle framework do not execute. No legacy materializer is invoked.

Source SHA256: `12aef930a30278285e306de805a416dd190c87aaa460e2911e6371db40af9a2c`.
Test SHA256: `63fd3e33607d39940f0df80202c33bc95dba3dc8b7f605a0bf17e14f4e43f1bf`.
Receipt SHA256: `97c987aa7fcd324bdd98d97c4e58330e1757d7121c76ef361c0a58e296a57a7b`.

Source landed at main commit `071eba7b0ba914bbeb9aa60d9fe465f627b1a91e`; tests at `f07c74562ad0f868313e12061cb8b5210ffec6ab`; receipt at `8c8010ad2a4ea58f25dc989d62a622bd206f32e9`. Path-scoped main writes preserve concurrent swarm changes; no detached integration branch is involved. Source and test server readback matched their executed Git blobs before this documentation write.

## The proved finite-corpus contract

For each valid record, the actual engine transition satisfies:

```text
inventory_after = inventory_before - own_actual_buys - rival_actual_buys
                  + visible_sales - actual_town_consumption

C5 lower_bound = rival_actual_buys + own_actual_buys
                - own_requested_buy_upper - visible_sales
              <= rival_actual_buys
```

Successful fills, not requested quantities, are counted. Own requests are an upper bound even when affordability, prior purchases, or shed room restrict actual fills. Raw caps are applied before parsing. Empty/tuple/unknown/capped-suffix rows, integer coercion differences, duplicated shops, multiple cadences, malformed callbacks, both seats, and negative public inventory are covered. This finite test corpus supports the source theorem; it is not exhaustive over every engine state.

At the $1 floor, a synthetic rival SELL(3) followed by BUY(3) has net demand zero while public inventory falls three. C5 correctly reports gross-buy lower bound three and declines relocation at the floor. The deliberately extreme WHEAT inventory `10**15` is a pricing-boundary microstate, **not a claim that this state is reachable during a default 720-step episode**. Other corpus states/cadences are also synthetic, not sampled field prevalence.

## The useful negative timing witness

Every timing pair first executes a real rival BUY(1), so the previous positive signal is genuine. The next rival action is not used as a policy input; it is varied only by the evaluator.

At prior public WHEAT inventory 9,997, with player 0 selling four units and the rival switching to SELL(4) at raw slot zero on the next callback, C5's delayed sale causes:

```text
delta_own_cash    = -5
delta_rival_cash  = +4
delta_cash_margin = -9
```

The strongest positive pair is +10 cash margin. Therefore a valid prior gross-buy signal alone does **not** prove that moving the next sale improves cash margin. This is an immediate-phase counterexample, not a full-game loss or an order to kill C5. Keep the existing feature OFF pending current-stack, opponent-diverse paired field evidence. Do not infer persistence, net demand, or profit from detector correctness.

## Reproduce

From the repository root, select the exact engine with its adjacent JSON. These variables are explicit so no incompatible production package is silently imported:

```sh
LAB="$PWD/revenue/kaggriculture/cloud-execution-lab"
DIR="$LAB/candidates/v4/research/c5-market-transition"
export C5_ORACLE_HELPER="$LAB/candidates/v4/donor/overlay/r04_c5_wheat_demand.py"
export C5_ORACLE_ENGINE="/absolute/path/to/reference/engine/kaggriculture.py"
cd "$DIR"
python -B -m unittest -v test_c5_market_transition_oracle.py
python -B -O -m unittest -v test_c5_market_transition_oracle.py
python -B c5_market_transition_oracle.py --engine "$C5_ORACLE_ENGINE" --helper "$C5_ORACLE_HELPER" --random-worlds 4096 --output /tmp/c5-normal.json
python -B -O c5_market_transition_oracle.py --engine "$C5_ORACLE_ENGINE" --helper "$C5_ORACLE_HELPER" --random-worlds 4096 --output /tmp/c5-optimized.json
cmp /tmp/c5-normal.json /tmp/c5-optimized.json
cmp /tmp/c5-normal.json RECEIPT.json
```

A changed helper or engine pin fails rather than silently inheriting this receipt. Re-review and rerun against any successor. Existing integration owners retain the `M1 -> EOD_CAPACITY_RESCUE -> B10 -> C5` ordering; this research does not edit shared wiring, configuration, defaults, production runtime, workflows, archives, or Kaggle submissions.
