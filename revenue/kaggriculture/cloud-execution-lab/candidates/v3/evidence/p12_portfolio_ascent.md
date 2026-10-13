# P12 — monotone multi-product SELL coordinate ascent

## Source-real defect

At exact `main@2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb`,
`SellScheduler.act()` evaluates every target product but retains only one
`best=(item, plan, info)`. The returned market therefore cannot express two
independent, strictly robust product improvements on the same turn even when
raw order slots and post-unit stock permit both.

## Repair boundary

`p12_portfolio_ascent.py` is an additive wrapper around the incumbent scheduler.
It preserves the incumbent returned action and selected product, then considers
all other evaluation certificates in descending worst-case-gain order. An
extra current-turn SELL is appended only when:

1. `worst_relative_gain` is finite and strictly positive;
2. the candidate's cumulative sold units never trail its own incumbent
   reference at any checkpoint (aggregate shed occupancy cannot get worse);
3. the raw market list remains within `maxMarketOrdersPerTurn`; and
4. total current SELL quantity cannot exceed the evaluator's post-unit stock.

The overlay does not mutate future-plan state. TITAN replans from the next
observation, avoiding a second ownership claim over scheduled-tranche custody.
It also does not change receipt valuation, purchase projection, pressure order,
canonical package bytes, runtime pointers, or Kaggle state.

## Integration

```python
from p12_portfolio_ascent import install
selected = install(existing_sell_scheduler)
action = selected.act(obs, configuration)
```

## Executed evidence

The stdlib-only suite contains 17 predecessor and adversarial contracts for two
simultaneous robust products, multi-addition, raw-cap contention, deterministic
gain/tie order, delayed-sale rejection, malformed/nonfinite certificates,
post-unit quantity bounds, repeated existing SELL rows, input nonmutation,
future-only no-op behavior, wrapper diagnostics, and fail-closed configuration.

Exact local mirror receipts:

- overlay SHA-256: `5d60c30d0fae80bc1de6f634a5502e249cc87d644939e5a2e1973f6e08d2285d`
- test SHA-256: `8f374136abf952bd380abda3113f29dd96ea57aa4080f21867457f83a7079a3c`
- `python -m unittest -v test_p12_portfolio_ascent.py`: 17/17 PASS
- `python -m py_compile ../overlay/p12_portfolio_ascent.py test_p12_portfolio_ascent.py`: PASS
