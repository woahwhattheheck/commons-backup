# Forward procurement: storage and cash are part of the price

This is an executable mechanism study in the existing `fwd-buy-census` family,
not another FWD policy, census decoder, V4 branch, or activation recommendation.
The earlier census and its verified-loader repair remain unchanged.

## What the actual interpreter demonstrates

All trajectories are constructed day-3 states. CARROT is mature in this period;
no late-game milk-production premise is smuggled into the proposed days-0..3
FWD window. These are not claims that a native agent reached the fixtures.

**Storage counterexample.** The farm has 96 CARROT in its 100-slot shed and
harvests 4 more at step 92. Buying 4 WHEAT at 92 costs $106; buying those same
4 at step 97 costs $109. The early purchase appears to save $3. However,
its WHEAT occupies the last four shed slots at EOD95, discarding the carried
CARROT. The identical step-96 sale receives $2,642 instead of $2,738. Net
own-cash and cash-margin change is **-$93**, with equal final WHEAT quantities,
both farms, and both private inventories. The rival passes and its cash is
unchanged. The shared market can differ, so this is not all-future-state
or game-level dominance.

**Liquidity counterexample.** With $26 cash, buying WHEAT1 at step 90 exhausts
cash before the authored $1 HIRE at 91. The missing worker cannot execute its
HARVEST92 / DROP93. The JIT arm sells the harvest for $135, pays the $1 hire and
the same $26 input cost, and finishes **$134 ahead**. A common later DIG clears
the unharvested annual crop; both arms end with equal farms and private stocks,
including WHEAT1. At initial cash $27, both hires succeed and both finish with
$135. This is an exact cash-threshold opportunity, not a blanket buying veto.
The raw nonexistent-hand HARVEST row is preserved and sent to the interpreter,
not truncated by a stricter evaluator.

**Counter-control.** Buying early, selling the WHEAT before EOD, and reacquiring
it at 97 finishes **$1 above JIT** in the storage witness, with equal final
physical state and shared market inventory. Therefore the evidence does not
justify saying that every early purchase is dominated. Public town demand,
liquidation timing, rival supply, financing, and headroom must be considered
separately. This pass-rival result is not a tradable guarantee against opponents.

## Declared panel and checks

The complete declared headroom matrix has 540 cells: both seats; quantity
1/2/4/8/20; room equal to quantity, quantity+4, or 100; CARROT harvest 1/2/4;
WHEAT inventory 9996/10000/10020; zero or one BAKERY. Each cell executes all
three arms for six callbacks. No cells are filtered. Early-hold margin signs
are 180 negative, 240 positive, and 120 equal; its range is -$96 to +$11.
Exactly 180 cells lose harvest. These counts describe a constructed grid,
not probabilities, a game win rate, or estimated field value.

The panel is 9,720 full official-interpreter calls per execution. The complete
report, including the named witness and both-seat capital controls, is 9,802.
The separate 17-test suite executes 9,998 calls in each normal/optimized mode.
Three broken experiment variants fail by behavioral assertions (6/3/3 failures)
in both modes, with zero test-execution errors. Missing or changed source inputs
fail closed. Loading ignores stale bytecode and restores the prior import table.
No game function or price function is stubbed. The exact upstream seed helper is
compiled from authenticated `utils.py`; fixtures are initialized explicitly.

## Reproduce without network, Kaggle installation, or Actions

Use the three official source files already included in the current exported
runtime at `checks/reference/engine/`. The checker verifies their exact Git
blob IDs before executing the same bytes. The existing artifact 10175943272
contains archive `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
No artifact rebuild is needed.

From this directory, set `ENGINE` to that extracted `checks/reference/engine`
directory, then run:

```sh
python check_opportunity_cost.py --engine-dir "$ENGINE"
python -O check_opportunity_cost.py --engine-dir "$ENGINE"
python opportunity_cost.py --engine-dir "$ENGINE" --output panel.json
python -O opportunity_cost.py --engine-dir "$ENGINE" --output panel-O.json
cmp panel.json panel-O.json
python check_opportunity_cost_mutations.py --engine-dir "$ENGINE" --output mutations.json
```

`OPPORTUNITY_COST_EXECUTION.json` preserves exact source hashes, stdout, mutation
results, output digest, and execution limits. The large generated panel is not
committed; the commands reproduce every declared row and its exact output hash.

## Integration boundary

Muse's rejected/noisy FWD-BUY gate remains parked. The advertised helper
`bd80e0da426192f0272abc8300f9f1845bab87cc` was not retrieved or executed here;
these are source-independent economic counterexamples, not proven defects in
that helper. No runtime, configuration, archive, decoder, workflow, production
default, or Kaggle submission changes. Existing current-runtime and field-gate
owners retain exact-donor engagement, opponent-diverse games, callback deadlines,
and future-harvest/funding controls before any activation.
