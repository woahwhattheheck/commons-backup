# TITAN V4 PHASEBARRIER

`PHASEBARRIER` is a **research/checker** for one official interpreter causality rule:
all farmer/hand unit actions execute before the callback's market orders. A unit action
therefore cannot consume an item, seed, animal, or newly hired actor acquired by a
market row in that same callback.

This package has **no gameplay, scheduling, composition, default, or promotion
authority**. It does not rewrite actions. It is intended to reject impossible planner
assumptions and to provide a regression contract for the one canonical V4.

## Source custody

The checker pins the official engine Git blob exactly:

- `reference/engine/kaggriculture.py`
- blob `3c202c7ee921da239356789e266b694635103fc4`

`certify_engine_source()` also parses the pinned source and independently requires all
`_apply_unit_action(...)` calls in `interpreter()` to occur before its sole
`_process_market(...)` call. Exact-byte custody alone is not treated as a phase proof.

## Detected impossible dependencies

Given an exact pre-callback resource snapshot and the authored response,
`detect_same_callback_dependencies()` reports only dependencies that a same-callback
market row could falsely appear to satisfy:

| Unit-side demand | Later market row | Result |
| --- | --- | --- |
| aggregate `PLANT crop` demand exceeds pre-callback seeds | `BUY_SEED crop` | `BUY_SEED_AFTER_PLANT_PHASE` |
| actor lacks carried WHEAT for `FEED` | `BUY_PRODUCT WHEAT` | `BUY_PRODUCT_AFTER_FEED_PHASE` |
| actor lacks carried FERTILIZER for `FERTILIZE` | `BUY_PRODUCT FERTILIZER` | `BUY_PRODUCT_AFTER_FERTILIZE_PHASE` |
| `PICKUP item qty` exceeds pre-callback shed stock | relevant `BUY_ANIMAL`/`BUY_PRODUCT` | `BUY_AFTER_PICKUP_PHASE` |
| actor lacks carried animal for `PLACE animal` | `BUY_ANIMAL animal` | `BUY_ANIMAL_AFTER_PLACE_PHASE` |
| authored non-PASS action targets a hand that does not yet exist | `HIRE` | `HIRE_AFTER_UNIT_PHASE` |

The detector is deliberately **not** a general legality checker. If a unit action is
illegal for an unrelated reason, PHASEBARRIER stays silent unless a relevant same-step
BUY/HIRE could be mistaken for valid funding. Existing pre-callback inventory suppresses
the corresponding warning.

Only the executable market prefix is credited. The snapshot may provide
`max_market_orders`; it defaults to the current V4/engine-config value of `10`. Rows
beyond that prefix cannot create a false dependency here.

## Snapshot contract

The pre-callback snapshot is intentionally small and explicit:

```json
{
  "seeds": {"WHEAT": 1},
  "shed": {"SHEEP": 0},
  "inventories": [{}, {"WHEAT": 1}],
  "existing_hands": 1,
  "max_market_orders": 10
}
```

`inventories[0]` is the farmer and following entries are existing hands in index order.
Counts must be nonnegative exact integers. Shape ambiguity fails closed.

## Run

From this directory:

```bash
python -m unittest -v test_phase_barrier.py
python -O -m unittest -v test_phase_barrier.py
python phase_barrier.py
```

The CLI always certifies the official engine first. Optional `--snapshot-json` and
`--action-json` arguments emit an audit receipt. `audit()` advertises
`decision_authority=false`; a clean receipt means only that none of the covered
same-callback market dependencies were detected.

## Evidence boundary

Focused authoring tests cover exact source custody, phase-order mutation rejection,
BUY_SEED/BUY_PRODUCT/BUY_ANIMAL/HIRE latency, pre-existing-resource non-blocking,
market-prefix truncation, and malformed snapshot refusal in both normal and optimized
Python. This package does **not** claim current-native engagement or economic strength;
those require a concrete planner/composition consumer with authentic pre-state.
