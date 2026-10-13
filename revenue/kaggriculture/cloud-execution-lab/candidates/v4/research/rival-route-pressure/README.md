# TITAN V4 PARALLAX — public rival-production route pressure

**Disposition: research-only / no decision authority / no runtime activation.**

PARALLAX closes a missing analysis seam inside the **single existing V4**: the frozen Arlene production controller has four inherited route IDs and three explicit route switches, but those switches use only `shop_YARN_STORE` at step 226, `px_CARROT` at 360, and `inv_MILK` at 433. Public rival farm production is not part of route admission. The existing SELL scheduler *does* use public rival standing/harvested yield for sale-timing stress, so this package deliberately does **not** duplicate sale scheduling. It asks whether a production-route switch increases future requested SELL exposure into a commodity where public rival standing yield is already visible.

## Exact source boundary

Current source observed when this package was built:

- parent: `reference/next-panel/vendor/arlene.py`, Git blob `bdb9cf58148a3c7961c085f4902759537decabf6`
- official engine: `reference/engine/kaggriculture.py`, Git blob `3c202c7ee921da239356789e266b694635103fc4`
- parent route switches: `(226, shop_YARN_STORE -> YARN)`, `(360, px_CARROT -> YARN_CARROT)`, `(433, inv_MILK -> MILK_GLUT)`

`current_route_probe.py` refuses parent-source drift by exact Git-blob identity before decoding the current route tapes.

## What the analyzer proves

`rival_route_pressure.py` provides four bounded pieces of evidence:

1. **Executable route SELL signatures.** Raw rows beyond `maxMarketOrdersPerTurn` are excluded independently per callback.
2. **Every inherited branch pairing.** `branch_catalog()` compares every possible incumbent route against every authored target instead of assuming one route history.
3. **Public rival signal only.** It reads current rival crop/animal tile `yield_units`, counts productive tiles, and separately records publicly collectable fertilizer flags. It never reads or infers rival shed/inventories.
4. **Known town drain only.** It counts consumption from shops already present in public `town.unlocked_shops` plus the town center. Future shop unlocks depend on hidden episode RNG and are intentionally not predicted.

`route_pressure_report()` emits `public_pressure_units = max(0, incremental_target_sell + visible_rival_standing_yield - known_current_shop_absorption)`. That is a **witness**, not a price/score theorem: route SELL requests may not fill, visible yield may never be harvested/sold, and unknown future shops may add demand.

The report therefore contains **no allow/deny/choose bit**. It is intended to falsify or prioritize branch hypotheses before an expensive both-seat current-native economics gate. Production wiring needs a separate exact-engine field receipt.

## Reproduce

Focused dependency-free contract:

```bash
cd candidates/v4/research/rival-route-pressure
python -m unittest -v test_rival_route_pressure.py
python -O -m unittest -v test_rival_route_pressure.py
python -m py_compile rival_route_pressure.py current_route_probe.py test_rival_route_pressure.py
```

Source-bound current-route catalog from `cloud-execution-lab`:

```bash
python candidates/v4/research/rival-route-pressure/current_route_probe.py \
  --parent reference/next-panel/vendor/arlene.py \
  --expected-git-blob bdb9cf58148a3c7961c085f4902759537decabf6 \
  --output /tmp/parallax-current-routes.json
```

To add public pressure rows, supply a real public observation/configuration JSON pair from an existing native runner. Do not fabricate rival private inventory, seed, or future shop identities.

## Non-overlap / handoff

- SELL timing / sale-window / market-pressure owners retain sale scheduling and final queue transforms.
- Market-baseline / town-curve owners retain exogenous market priors.
- Opponent/gauntlet owners retain opponent packaging and field execution.
- Existing native composer retains whole-stack materialization.

PARALLAX owns only **production-route admission evidence against visible public rival supply across all inherited route branches**. If current-native controls find no natural engagement or no economic gain, keep this as a falsifier and do not wire it into `main.py`, `titan_runtime.py`, config, archive, workflow, or Kaggle submission.
