# TITAN V3: proven-executable HIREs in represented event horizons

## Exact seam

Audited base: `c51049d671b55d282e0fed5df37a0be7c513a838`  
Canonical source: `revenue/kaggriculture/cloud-execution-lab/frozen_selected.py`  
Canonical Git blob: `fc7baf5c179818a55037f6a61d92984d81d1a21c`

`apply_represented_market` currently spawns a copied hand for every authored
`HIRE`, although it has no engine receipt and does not debit cash. The copied
hand can then execute future `PICKUP`/`DROP` rows inside
`represented_shed_event`; a false post-baseline shed increase reaches
`end=max(end, unit_event)` and changes the SELL optimizer's horizon.

The canonical file already contains the correct HIRE-cost primitive in its
funding simulator:

```python
m._hire_cost(hires, int(config.get('farmHandCostMult', 1)))
```

This refined carrier uses that native oracle and tracks a conservative lower
bound on cash in the represented copy.

## Sound lower-bound rule

For HIRE admission only:

- start from copied post-unit cash and `hires_today`;
- ignore SELL proceeds, because missing rival/quote chronology means they are
  upside but not guaranteed cash;
- after any represented `BUY_PRODUCT`, `BUY_ANIMAL`, `BUY_SEED`, or `BUY_LAND`,
  set the later-HIRE cash lower bound to zero rather than pretending the buy was
  free;
- debit each provably funded HIRE by the native Fibonacci-scaled cost and
  increment `hires_today`;
- spawn the copied hand only when the lower bound covers that cost.

This admits every HIRE funded without uncertain sale credit or unmodeled prior
purchase spend. It deliberately rejects ambiguous HIREs. The result cannot
manufacture an actor from zero cash, while a plainly funded HIRE remains
represented.

## Relationship to the first carrier in PR #12055

The sibling `v3_event_horizon_executable_hire` carrier is a strict control that
skips every unverified represented HIRE. This refined carrier is the preferred
candidate: it preserves provably funded HIREs and therefore narrows the false-
negative surface. Keeping both makes a useful three-arm causal panel:

1. canonical predecessor;
2. skip-all-HIRE control;
3. proven-HIRE candidate.

A score change shared by arms 2 and 3 is attributable to removing phantom
workers; a difference between arms 2 and 3 measures the value of retained,
provably funded represented workers.

## Contracts

The suite covers source drift, five unique source replacements, zero-cash
phantom HIRE, funded-HIRE preservation with exact debit, Fibonacci prefix
`1+1+2`, ignored SELL-credit uncertainty, prior-buy lower-bound invalidation,
the score-facing future `PICKUP`/`DROP` witness, an existing-worker control,
round-trip bytes, and the real canonical blob in CI.

Local source-shaped result: 11 passed, 1 canonical-source test skipped. In
repository CI all 12 are enabled.

## Admission boundary

`HOLD_FOR_PAIRED_PANEL`. The carrier changes only an additive materialized
candidate; canonical runtime, emitted actions, release pointers, archives, and
Kaggle state remain untouched. Run the three-arm exact-source panel on every
route/seat/seed cell where a represented HIRE precedes a post-baseline hand
command. Require real action activation, zero new losses/lost wins, positive
own value, nonnegative opponent-by-seat tails, and manual inspection of every
changed trace before one-tree integration.
