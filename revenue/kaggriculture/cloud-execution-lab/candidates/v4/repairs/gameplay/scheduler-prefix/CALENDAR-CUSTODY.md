# TITAN V4 scheduler source custody

Status: **SOURCE-BOUND CANDIDATE / DEFAULT-OFF / NO PRODUCTION MUTATION**

This is the same second-stage repair already landed in the existing `scheduler-prefix`
authority by #13091. The successor widens that one materializer instead of creating
another scheduler/controller layer. It still consumes the exact scratch output of
`materialize_scheduler_prefix.py` and never edits `scheduler.py` in place.

## Closed source seams

Calendar custody remains unchanged: HIRE-day reset, represented future unit day/turn
arguments, represented EOD drop, planning-horizon day end, and naive EOD handling all
derive from the configured `turnsPerDay`; canonical 24 behavior is preserved and
malformed calendar evidence fails closed.

The same source also contained a separate executable-market inconsistency. The
canonical prefix projection already models the official interpreter's
`max(1, int(maxMarketOrdersPerTurn))`, but two later `SellScheduler.act()` guards used
the raw configured integer:

- feasibility rejected a planned sale whenever `len(orders) >= raw_cap`;
- append admission required `len(market) < raw_cap`.

At raw cap `0` or any negative cap those guards treated the market as having zero
rows, while the official interpreter executes at least row zero. The successor
extracts one `_engine_market_limit(config)` from the already-authenticated prefix
rule, uses it in `_engine_market_prefix()`, binds it once in `act()`, and routes both
guards through that same value. Existing int-coercion behavior is intentionally
preserved; this patch fixes minimum-one parity rather than inventing a new config
typing policy.

## Bound composition

1. raw scheduler Git blob `a483b24dd72b580d7d8811636b54d2d44f391575`;
2. canonical prefix materializer Git blob `f36e9120ea07c861a7eca5821a5306c6dbfa4613`;
3. exact prefix scratch output Git blob `1da9934ec45f485a16244bcbc78af26d9109b97e`;
4. official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`;
5. `materialize_scheduler_calendar.py` applies calendar custody plus shared
   minimum-one market-limit custody.

## Validation receipt

Exact authored candidate against the bound prefix/engine bytes:

- focused suite: **18/18 PASS** normal;
- focused suite: **18/18 PASS** under `python -O`;
- `py_compile`: **PASS**;
- exact CLI scratch materialization: **PASS**;
- candidate scheduler Git blob: `2fb6908282cfcd99d3745ff0ca96bc7c1361ae0a`.

New cap regressions prove cap `0` and negative caps retain one executable row, cap
`1` is identical, both `act()` guards use the shared effective limit, and the prefix,
scheduler guards, and exact engine source are bound to one minimum-one theorem. The
prior calendar/source-drift/double-apply/exclusive-output contracts remain green.

## Boundaries

No runtime/default/config/COMPOSITION/INTEGRATION/archive/Kaggle change and no gameplay
or economics promotion claim. The separately claimed represented physical-transition
lane retains purchase/HIRE execution authority. This artifact owns scheduler calendar
and executable market-cap source parity after canonical executable-prefix composition.
