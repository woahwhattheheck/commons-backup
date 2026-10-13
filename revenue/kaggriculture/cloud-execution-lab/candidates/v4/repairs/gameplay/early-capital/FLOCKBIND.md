# ASTRA-FLOCKBIND recovery — dependent-animal capital rebind

Canonical home: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/early-capital`.

This is an additive, default-OFF source successor inside the existing early-capital family. It is **not** a second V4, controller, route selector, feature default, archive, or Kaggle submission.

## Recovered failure and stronger design

The abandoned FLOCKBIND session isolated a current-route capital mismatch on authenticated artifact `10175943272` / official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`: a full day-start market queue bought deferable WHEAT/STRAWBERRY seed inventory and preserved eight HIRE rows, while the next callback authored `BUY_ANIMAL SHEEP 0`; later callbacks still authored SHEEP `PICKUP` then `PLACE` and service work.

A hard `STRAWBERRY4 -> SHEEP1` replacement was falsified on seed 101. The stronger zero-credit design is temporal rather than preferential:

1. prove the current market prefix is exactly full and contains one positive WHEAT seed row, one positive STRAWBERRY seed row, and only HIRE rows otherwise;
2. prove from the exact parent route that a zero/non-positive SHEEP buy is followed by SHEEP `PICKUP -> PLACE`, with no positive SHEEP buy before pickup;
3. prove a later parent-empty market callback exists after placement and before the first authored WHEAT `PLANT`;
4. use **observed current cash only** to replace the current WHEAT row one-for-one with `BUY_ANIMAL SHEEP 1`, preserve every HIRE, and keep the maximum affordable positive STRAWBERRY quantity;
5. carry the displaced WHEAT quantity as an explicit obligation;
6. backfill it only on an authenticated parent-empty callback with observed cash sufficient for the exact fixed WHEAT seed cost, before the first authored WHEAT plant.

There is no future SELL credit, guessed fill, row-count expansion, or step-number-only policy. Parent action drift, source drift, malformed route state, shed-capacity pressure, pre-existing carried SHEEP, non-empty backfill market, insufficient observed cash, or deadline crossing all fail closed to the parent action.

## Exact source bindings

`dependent_animal_rebind.py` carries immutable bindings for:

- official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`
- current Arlene parent Git blob: `bdb9cf58148a3c7961c085f4902759537decabf6`

Callers must authenticate those bytes and pass `source_bound=True`; the helper also requires explicit `enabled=True`.

The unit-phase projection intentionally mirrors the already-landed `early_capital.py` contract so the SHEEP shed-capacity check is post-unit rather than guessed from the pre-turn observation. The existing pinned `early_capital.py` is untouched by this recovery.

## Recovered field evidence — not promotion authority

The stale session reported the following official-engine results against the intact artifact before it disappeared:

- final zero-credit design, seat 0, seed 17: **+25,744 own / +25,834 margin**
- final zero-credit design, seat 0, seed 101: **+4,995 own / +5,163 margin**
- hard replacement falsifier, seed 101 mirrored seats: **-19,091 own / -18,932 margin**
- timing-swap falsifier, seed 17: **-5,280** (reported delta; no durable widened receipt was published)

The session explicitly stopped before a source/ref write and before widening the final design across both seats/additional seeds. Those numbers are therefore preserved as recovered design evidence only. They are **not** a current-native both-seat promotion claim.

## Focused authored-byte checks

The additive helper and its test file pass:

```text
python -B -m unittest -v test_dependent_animal_rebind.py
13/13 PASS

python -O -B -m unittest -v test_dependent_animal_rebind.py
13/13 PASS

python -B -m py_compile dependent_animal_rebind.py test_dependent_animal_rebind.py
PASS
```

The focused suite locks:

- the seed-17 `STRAWBERRY4 -> STRAWBERRY1` affordability witness;
- the seed-101 `STRAWBERRY4 -> STRAWBERRY3` affordability witness;
- preservation of all eight HIRE rows and market cardinality;
- no future-SELL credit;
- required zero-SHEEP-buy / PICKUP / PLACE / WHEAT-PLANT causality;
- rejection when a real positive SHEEP purchase already exists;
- exact full-prefix and parent-action custody;
- post-unit shed capacity / pre-existing SHEEP refusal;
- disabled and unbound identity;
- exact parent-empty WHEAT backfill at observed cash 40;
- refusal at cash 39, non-empty market, non-parent callback, and deadline;
- Git-blob identity semantics.

These are source/helper tests, not a full current-native field panel.

## Next gate

Compose this helper through the **existing** early-capital/native graph only. The next owner should authenticate current postimages, prove natural FLOCKBIND engagement on both seats, execute a wider seed panel against current opponents, and report exact terminal own/rival/margin plus fallback/deadline/obligation telemetry. If the exact current route no longer presents this dependency chain, disposition must be COLD/UNREACHED rather than weakening the source or route pins.

No runtime/default/config/archive/Kaggle activation is authorized by this package.
