# COBUY — simultaneous BUY_PRODUCT lockstep quote oracle

Status: **research / mechanism only**. This lives in the existing V4 `research/market-baseline/` authority and does not add a controller, runtime hook, feature key, default, archive, or Kaggle activation.

## Source theorem

Pinned official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

For each raw market-order index, `_process_market()` parses both seats, then runs a per-unit lockstep loop. For every still-active `BUY_PRODUCT WHEAT|FERTILIZER` order it first quotes both seats from the **same pre-commit public inventory** using:

```python
market_price(item, market["inventory"][item] - 1, market.get("params"))
```

Only after both quotes exist does it commit the two units. Each successful buy decrements public inventory by one. Therefore equal-item buys aligned on the same raw order index share the first-of-pair quote. If our required buy is delayed until after the rival's order has completed—or merely placed on a later raw order index in the same callback—we instead pay the deeper-scarcity curve.

This is distinct from SELL-side `lockstep_join`: COBUY is a BUY_PRODUCT current-cost theorem and legal BUY_PRODUCT items are only `WHEAT` and `FERTILIZER`.

## Executable witnesses

`lockstep_cobuy_oracle.py` imports the exact pinned engine and calls its real `_process_market()` implementation. It compares worlds with identical purchased quantities and terminal public inventory:

| Item | Rival qty | Our qty | Same-row cost | Wait-behind cost | Saving |
| --- | ---: | ---: | ---: | ---: | ---: |
| WHEAT | 100 | 100 | $3,445 | $3,720 | $275 |
| FERTILIZER | 100 | 100 | $12,000 | $13,010 | $1,010 |
| WHEAT | 50 | 100 | $3,393 | $3,490 | $97 |

The 100-unit witnesses are intentionally bounded by the default `shedCapacity=100`; the oracle refuses larger quantities instead of silently relying on hoisted inventory or a non-default configuration.

A raw-row alignment control inserts an invalid zero-quantity SELL at our row 0 and moves our buy to row 1. The rival's row-0 buy then completes before our row-1 buy begins, producing exactly the wait-behind cost. Other controls prove zero saving when the rival buys nothing and zero cross-item effect when the rival buys WHEAT while we buy FERTILIZER.

## Commands

From this directory in a full checkout:

```bash
python -B test_lockstep_cobuy_oracle.py
python -O -B test_lockstep_cobuy_oracle.py
python -B lockstep_cobuy_oracle.py --item WHEAT --self-qty 100 --rival-qty 100
python -B lockstep_cobuy_oracle.py --item FERTILIZER --self-qty 100 --rival-qty 100
```

Both source files fail closed if the official engine Git blob drifts.

## Boundary / next gate

This package **does not claim predictive access to the rival's current private action**, current-native engagement, or positive field EV. A policy successor is admissible only if existing public opponent-flow/current-route evidence can predict a rival WHEAT/FERT procurement pulse early enough to retime an **already-required** own acquisition without changing quantity, violating cash/shed capacity, displacing feed/fertilizer obligations, or exceeding raw market-row budget. That successor belongs in the existing opponent-intel/market integration family, not in a COBUY controller.

Required next evidence is a current-native/replay collision census keyed by `{step, raw_order_index, item, rival_filled_qty, own_required_qty}`. Zero lawful predictable collisions => COLD/research-only. Positive collisions still require exact OFF identity and both-seat economics before any activation language.
