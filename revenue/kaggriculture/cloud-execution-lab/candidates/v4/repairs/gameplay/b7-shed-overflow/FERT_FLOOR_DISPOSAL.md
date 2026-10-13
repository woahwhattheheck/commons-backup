# FERT floor disposal: capacity relief, not a warehouse

This packet extends the existing canonical `b7-shed-overflow` family. It is a correction and admission surface for the Riot/Muse `r04_fert_warehouse` carrier, **not** a second controller and **not** an activation.

## Exact engine correction

Official engine blob `3c202c7ee921da239356789e266b694635103fc4` makes floor-price FERT sales destructive custody:

- `SELL` always removes the sold unit from the player's shed and pays the quoted price.
- Public market inventory increments only when the SELL quote is greater than the `$1` floor.
- `BUY_PRODUCT FERTILIZER` later consumes whatever shared public stock exists and quotes against post-buy inventory. It does not recover the unit that vanished on a floor sale.
- FERT is absent from town/shop consumption, so unilateral above-floor supply reaches the first `$1` quote at public inventory `10493` under the pinned parameters and then stops admitting additional sold units. A simultaneous two-seat stale quote can overshoot by one to `10494`.

`check_fert_floor_engine.py` executes the exact market loop. From inventory `10492`, one seat selling 100 FERT ends at public inventory `10493`, earns `$101`, and immediately buying 100 back costs `$1,150`. With both seats selling 100 simultaneously, public inventory ends at `10494`, each earns `$101`, and one 100-unit buyback costs `$1,130`. Therefore the old “zero-friction infinite off-site warehouse” interpretation is false.

## What remains useful

A `$1` sale can still be a **paid disposal** that opens shed room before the EOD inventory sweep. `fert_floor_disposal.py` does not perform that sale. It returns a fail-closed capacity certificate containing only the minimum FERT quantity whose disposal would make all currently carried inventory fit after conservatively reserving current `BUY_PRODUCT` / `BUY_ANIMAL` arrivals.

The analyzer:

- runs only on EOD and only at an observed `$1` FERT quote;
- consumes the current selected action through the injected current `post_units` ABI;
- refuses a full market queue, malformed state, or an existing FERT market touch;
- accounts for post-unit shed stock, all carried inventories, shed capacity, and current requested shed buys;
- requires current FERT stock to cover the entire certified overflow;
- reports the exact same-public-state immediate rebuy cost as a diagnostic;
- always emits `warehouse=false`, `recoverable_custody=false`, and `economic_authorization=false`.

A future B7/value owner may compare the cargo saved with the opportunity cost of destroying FERT, then consume the proposed quantity. This packet intentionally does not make that economic decision.

## Current-ABI witness

`check_fert_floor_current_abi.py` binds the analyzer to authenticated native runtime blob `b952c9c228ecbde592bf3d2df01638677abb0d24`, scheduler blob `a483b24dd72b580d7d8811636b54d2d44f391575`, and the exact official engine. In both seats, a constructed EOD state with 90 shed units (20 FERT + 70 CARROT) and 20 carried WHEAT produces a minimal `SELL FERTILIZER 10` capacity proposal. The unchanged interpreter then shows baseline WHEAT deposit `10` versus candidate `20`, while FERT falls from `20` to `10`, cash rises by `$10`, and public FERT inventory stays `10493`. The saved capacity is real; the sold stock is not warehoused.

## Boundaries

- No `Features` field, config key, production/default/archive/Kaggle mutation, or runtime hook is added.
- No high-price FERT seller is added. Existing SELL / HERDSCALE / operating-stock ownership remains authoritative there.
- No B7 activation is authorized. Its existing multi-turn cargo-priority hold remains intact.
- The Riot/Muse carrier's mechanics evidence is not claimed as exact-byte custody here; this is an independent source-bound correction derived from the official engine and authenticated current ABI.

## Reproduce

```bash
B7=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/b7-shed-overflow
python -B "$B7/test_fert_floor_disposal.py"
python -O -B "$B7/test_fert_floor_disposal.py"
python -B "$B7/check_fert_floor_engine.py" \
  --engine revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py
# For the exact native-package witness, materialize the authenticated runtime and run:
python -B "$B7/check_fert_floor_current_abi.py" --runtime-root /path/to/runtime
python -O -B "$B7/check_fert_floor_current_abi.py" --runtime-root /path/to/runtime
```
