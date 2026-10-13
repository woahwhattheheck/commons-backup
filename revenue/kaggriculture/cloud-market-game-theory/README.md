# T15 complete-plan market game theory

Runnable research over the accepted T12 causal history and frozen SELL parent.
Selected TITAN remains unchanged. The T11 and T12 completed panels are retained.

`solver.solve_table(D)` solves a finite zero-sum receipt table with a zero
baseline row and at most two complete alternatives, exactly using rational
arithmetic. It maximizes the worst **expected** own-minus-rival cash change over
the supplied correlated rival streams. Alpha is zero; no calibrated scenario
probabilities are available. `tables.best_pair` compares these exact restricted
tables over at most nine independently feasible caller plans. This is a bounded
support search, not the unrestricted optimum over mixtures of three or more
alternatives or a whole-game equilibrium.

`WholePlanSelector.transform(observation, configuration, supplied_action,
window=..., post_unit_shed=..., reservations=..., feasible=...)` accepts one
authoritative action. A window contains `key`, `item`, `quantity`, `now`, `end`,
fixed `slot`, complete `plans` and baseline-relative `deltas`. Each plan has
`id` and `sales: [[absolute_step, quantity], ...]`. The caller's deterministic
feasibility function checks every constituent's dated production/capacity,
funding and future order positions. Current operating cash and stock are checked
separately. The selector samples once per committed lot, retains that complete
choice through later actions and retries, and preserves unit actions and other
market products. A changed physical or slot constraint returns the supplied
action and records an aborted commitment. Its original expected bound applies
to execution of the complete conditional plan.

`runtime.MarketGameTheory` is the research bridge. It calls one unchanged
T12/SELL parent, captures already-computed feasible plans, consumes T12's whole
historical streams, then invokes the transform. It builds no additional
production controller. All current/future rival columns are hypotheses made
from causal public inputs. Evaluator-only private stocks and actual rival
orders never enter the policy. Fixed own slot positions are identical across
every column; rival before/paired/after slots are legal relative positions.

## Engine evidence

The first expanded scan found a TOMATO lot of eight at inventory10080, with
visible PIZZA_SHOP and FARMERS_MARKET demand. The frozen complete reference
sells2 now and6 at the window end. Alternatives sell4 now/4 at end or all8 at
end. Across28 quiet/quantity/date/slot streams the exact mixture weights are
4/7 and3/7, with worst expected relative receipt gain2/7. Each pure alternative
has a losing column. Three such tables match4536 official interpreter
transitions in both seats, including town consumption after market.

These are explicitly constructed legal-state regimes expanded from retained
development inputs, not reached full-game improvements. Initial retained-state
scanning did not itself produce a positive mixture. The earlier two-stream
STRAWBERRY table has rows `[0,0]`, `[1,-1]`, `[-1,2]` and expected gain1/5.
Adding the legal paired rival-sale column gives `[0,-1,-1]` down that column
and returns the solver to the baseline. This negative control also matches the
official engine in both seats. Larger omitted scenario families can alter a
finite-table bound; an expected bound permits individual realized losses.

Eleven focused test groups include80 independent SciPy LP comparisons, exact
fractions, whole-plan persistence, reservations and identical public inputs in
different simulator-private worlds. SciPy is only a test oracle; production
code uses the standard library. The corrected v2 source is frozen in
SOURCE-FREEZE.json; v1 source/freeze and its complete records remain preserved.
V2 ran96 new games and reused24 exact unchanged development controls. All120
games in that comparison complete719 decisions. It has no W/T/L improvement;
held endpoint choices lose4 own cash versus Apex in each seat, rival cash
unchanged. No nondegenerate mixture was selected in any full game. The v2 mixed
arm's maximum policy call is396.38ms and maximum RPC404.11ms. The archive's
official-loader first call is26.32ms on the retained compatibility check.

Across both versions,216 unique games were attempted and213 completed. V1's
three pure-arm held games ending at the RPC deadline remain recorded. Its four development
endpoint choices gain2 own cash each and flip two SELL ties; restored causal
history removes those choices' strictly positive table bound. These outcomes
are separate from the genuine nondegenerate constructed-engine tables.
RESULTS.json and RESULTS.md preserve exact cash pairs, runtime and limitations.
Selected TITAN stays frozen SELL; the T15 package is a callable research input.

Run from the repository root:

```sh
python -m unittest discover -s revenue/kaggriculture/cloud-market-game-theory -p 'test_*.py'
python revenue/kaggriculture/cloud-market-game-theory/scan.py --full --output /tmp/t15-scan.json
python revenue/kaggriculture/cloud-market-game-theory/engine_cases.py --engine-dir /path/to/engine --scan /tmp/t15-scan.json --output /tmp/t15-engine.json
```

Raw scan/engine reports are compressed as reproducible `.json.gz` files.
Engine source: Kaggle/kaggle-environments28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c,
Python SHA256bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e.
DEPENDENCIES.json records all reused code bytes. Source licensing is in NOTICE.md.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
