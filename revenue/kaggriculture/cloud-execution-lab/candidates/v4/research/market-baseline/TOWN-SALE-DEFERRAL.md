# TOWNSELL — deterministic post-drain sale premium

Research-only theorem donor inside the existing TITAN V4
`candidates/v4/research/market-baseline` authority.

## Result

Pinned official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`
processes each callback as **unit actions → market → town consumption**, and
`SELL` quotes each unit at the current pre-commit public inventory. A successful
sale at price `> $1` adds one unit to public inventory; a `$1` sale destroys
custody without increasing public supply. Town/shop demand then removes its
scheduled units and refreshes prices.

That yields a narrow deterministic theorem for an **already-intended identical
sale** under zero intervening rival market flow: if a known town drain of `d`
units occurs after this callback's MARKET phase, deferring the same item and
quantity to the next MARKET callback starts from inventory `I-d`. On the
official monotone inverse price curves, the post-drain sale revenue is never
lower than the pre-drain sale revenue. Price rounding can make the premium zero;
the theorem does not require it to be strictly positive.

The oracle reuses `town_wheat_timing.town_demand_units` and `sell_ledger`
instead of creating another market model. Its broad falsifier grid checks every
town-center-consumed product across public inventories `8,000–12,000`, town
drains `0–9`, and sale quantities `1/5/20/50/100` — **2,400 cells**. Zero-demand
cells must be exact revenue identities; any negative deterministic premium
fails the gate.

A concrete current-engine witness at inventory `10,000` uses five unlocked
MILK-consuming shop instances on step `100`. The scheduled drain is 5 MILK.
Selling 100 MILK before the drain returns `$6,205`; the identical sale after
that drain returns `$7,072`, a **+$867** deterministic timing premium in the
zero-rival mechanism witness. The focused test also executes `_process_market`
and `_town_consume` directly against the pinned official engine and requires the
engine-level revenue delta to match the pure ledger.

## Relationship to existing work

This is not a new merchant/controller.

- Historical V3 C4 already identified town-boundary sale reservation as an
  interesting held donor. This package carries that ancestry forward rather
  than relabeling it.
- V4 TOWNFLASH (`TOWN-WHEAT-TIMING`) proves the complementary WHEAT buy-before-
  drain effect and owns the exact demand/SELL ledgers reused here.
- Active TOWNPROCURE work owns any current-native WHEAT acquisition retiming.
  TOWNSELL does not touch that integration lane.
- Existing harvest/animal-product seller owners retain policy and runtime
  ownership. TOWNSELL is only a source-bound timing theorem they may consume.

## Promotion boundary

**Research only / default OFF.** A runtime consumer must separately prove that
one-callback deferral is safe for the specific authored sale: terminal horizon,
cash deadlines, shed/custody pressure, feed/seed/fertilizer obligations,
market-row budget, rival flow, opponent lockstep interaction, and any existing
seller ordering constraints can dominate the deterministic price premium.

No runtime, default, config, composition, archive, workflow, or Kaggle path is
changed by this package.
