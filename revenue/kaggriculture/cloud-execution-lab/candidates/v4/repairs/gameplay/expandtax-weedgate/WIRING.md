# R04-EXPANDTAX — wiring note (for the composer/integrator)

The carrier ships the decision function only. Runtime wiring is two lines at
the market-order surface plus one config key. Default OFF.

## Config

`TITAN-CONFIG.json`: add `"r04_expandtax": false`.

## Hook

Where the agent finalizes its market orders for the turn (v4: the return path
of the market-order builder in `r04_full_router.py`, before `return output`):

```python
if cfg.get("r04_expandtax") is True:
    from repairs.gameplay.expandtax_weedgate import expandtax
    action = expandtax.filter_market_orders(action, observation, cfg, books)
```

- `books` is an `expandtax.TrailingBooks` owned by the composer, fed once per
  day via `books.note_day(money, planted_tiles, non_pass_actions)`. Before the
  first day-over-day delta exists the books read 0.0 and the gate blocks
  (fail-closed: no expansion on day 0/1).
- OFF (`r04_expandtax` falsy/absent): `filter_market_orders` returns the action
  object unchanged — byte-identical to base.
- The hook never invents orders; it only strips BUY_LAND orders the gate
  rejects. Non-BUY_LAND orders pass through untouched.

## Why this surface

BUY_LAND is a market order (`["BUY_LAND"]` in `action["market"]`), so the
market-order boundary is the single choke point: one filter covers every
expansion-emitting policy without touching unit-action routing.
