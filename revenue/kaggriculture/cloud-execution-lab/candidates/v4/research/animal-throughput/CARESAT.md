# ASTRA-CARESAT — CARE-bank saturation boundary

This is research evidence inside the existing HERDSCALE animal-throughput authority. It does **not** add a controller, feature key, runtime hook, default, configuration field, archive, or Kaggle behavior.

## Exact engine theorem

The pinned official engine (`kaggriculture.py` Git blob `3c202c7ee921da239356789e266b694635103fc4`) updates an animal at EOD in this order:

1. update consecutive-unfed state and escape before production if the count reaches two;
2. on a production EOD, add the base unit plus the **previous** `pending_care_bonus` only when fed, cap stored product at species `max_held`, and reset the old CARE bank to zero;
3. only **after** that production step, if `cared_today && fed_today`, bank one CARE bonus for a later production;
4. reset `fed_today` and `cared_today`.

Consequences:

- CARE performed on a production day cannot increase that same EOD's product. It only banks a unit for a later cycle.
- An unfed production day still receives the base production unit if the animal survives, but the old CARE bank is erased unused.
- A second consecutive unfed EOD escapes before production and destroys the animal's stored CARE bank with the rest of the animal state.
- Product storage clips `base + old CARE bank` at `max_held`; excess old CARE units are real source-level saturation, not deferred value.

## First-yield saturation bound

Under the deliberately narrow premise “the newly placed animal is successfully FEED+CARE'd every day before first production, and no harvest can occur before first yield,” the CARE bank entering first production is `first_yield_day - 1`, while at empty product storage at most `max_held - 1` CARE units can join the mandatory base unit.

| species | first yield | max held | old CARE bank entering first yield | useful CARE capacity | source-certain clipped CARE |
| --- | ---: | ---: | ---: | ---: | ---: |
| GOOSE | 4 | 4 | 3 | 3 | 0 |
| COW | 8 | 6 | 7 | 5 | **2** |
| SHEEP | 6 | 6 | 5 | 5 | 0 |

That is **not** a claim that current Arlene actually wastes two CARE rows per cow. The premise requires successful target-specific FEED+CARE, realized placement, and no intervening state change. It is a source theorem showing that blanket daily pre-first-yield cow CARE can be overprovisioned even while every CARE action is individually legal.

## Current-route census boundary

`care_bank_oracle.py` reuses the already-authenticated `current_arlene_census.py` loader and reports only authored CARE/FEED pressure plus authored `PLACE COW` windows. Those windows are intentionally target-agnostic. They do not infer that a CARE row reaches that cow, that placement succeeds, that FEED succeeds, that product storage has headroom, or that final-return transforms preserve the row.

A gameplay consumer needs current-native, target-specific evidence before replacing any CARE row. W2/STARVE retains FEED-skip policy; ANIMAL-HEADROOM retains realized yield-cap execution; UNITRECYCLE retains same-callback predecessor-no-op replacements. CARESAT supplies only the delayed-bank/saturation state theorem and conservative route pressure.
