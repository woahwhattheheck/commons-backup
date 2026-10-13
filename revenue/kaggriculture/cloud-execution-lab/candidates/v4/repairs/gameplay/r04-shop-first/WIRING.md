# R04-SHOP-FIRST — wiring note (for the composer/integrator)

The carrier ships the decision function only. Runtime wiring is: one
composer-owned `ShopLedger`, one per-step feed call, one filter call at the
market-order surface, plus one config key. Default OFF.

## Config

`TITAN-CONFIG.json`: add `"r04_shop_first": false`.

## Ledger (composer-owned)

```python
from repairs.gameplay.r04_shop_first import r04_shop_first

ledger = r04_shop_first.ShopLedger()  # one per player/seat
```

Feed once per step, at observation time (before market-order construction),
with the transition into the current observation:

```python
ledger.note_step(
    step=observation["step"],
    shed_before=prev_observation["private"]["shed"],
    shed_after=observation["private"]["shed"],
    sells_issued={p: qty for p, qty in this_step_sells.items()},
    money_delta=observation_money - prev_observation_money,
)
```

On step 0 (no previous observation) skip the feed; the ledger starts
not-live, which is the correct fail-closed state.

## Hook

Where the agent finalizes its market orders for the turn (v4: the return path
of the market-order builder in `r04_full_router.py`, before `return output`):

```python
if cfg.get("r04_shop_first") is True:
    from repairs.gameplay.r04_shop_first import r04_shop_first
    action = r04_shop_first.filter_market_orders(action, observation, cfg, ledger)
```

- OFF (`r04_shop_first` not exactly `True`): returns the action object
  unchanged — byte-identical to base.
- Ledger not live (no shop tick observed within 48 steps): returns the action
  unchanged. On the pinned engine this is always the case.
- ON + live: only *reduces* positive SELL quantities of the nine
  shop-demand products, capping each so the SHOP_RESERVE floor survives.
  Never invents, reorders, or increases rows. Malformed observation/shed →
  unchanged (fail-closed).

## Why this surface

SELL rows are market orders (`["SELL", product, qty]` in
`action["market"]`), so the market-order boundary is the single choke point:
one filter covers every sale-emitting policy without touching unit-action
routing, exactly like the r04_expandtax precedent.
