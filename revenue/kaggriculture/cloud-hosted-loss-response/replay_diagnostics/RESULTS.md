# Actual hosted-loss findings — 7 September 2026

Both raw public replays were recovered byte-identically through the existing
ROWAN/ATLAS transport. Each720-frame replay supplies719 transitions. All1,438
transitions reconcile with the pinned official engine and both cash telescopes
have zero residual. Source, raw hashes and exact generated-file receipts are in
`results/HOSTED-RESULTS.json`; reproduction commands are in `README.md`.

## Loss106541578: market execution and excess purchases, not production

Our submission56081391 is seat1:95,995 versus96,979, a984 deficit. All720 complete
farm states are identical between players after excluding money. Unit execution,
harvesting, installed portfolios and production totals match throughout.

The final gap is an exact ledger identity:548 fewer sale receipts,196 more spent
on products,240 more spent on seeds. Relative sale proceeds by product are:
WOOL−249, MILK−284, FERTILIZER−101, CARROT−161, STRAWBERRY+85, WHEAT+159, EGG+3.
The seven extra WHEAT sale units reflect extra purchased goods, not production.

The first cash difference occurs at action236: one coin of fertilizer receipts.
The first deficit reaching the declared100-coin material threshold occurs at529:
the margin falls from−36 to−400. That turn's−364 swing includes−375 in WOOL
receipts, partly offset by+30 STRAWBERRY and+1 EGG, and−20 FERTILIZER. Identical
quantities at different market order positions encounter different shared supply.

An executable own-observation candidate ranks the initial SELL prefix by receipt
risk under an explicit equal-sized competing-lot scenario. At529 it changes
STRAWBERRY/MILK/WOOL/EGG/FERTILIZER to WOOL/MILK/STRAWBERRY/FERTILIZER/EGG, keeping
all quantities, unit actions, hire positions and the fertilizer purchase slot.
The real interpreter returns+201 own cash and−163 rival cash: a+364 relative
one-step change, with no own inventory or held-yield difference. It is not a
claimed full-game win and the scenario does not reveal the opponent's inventory.

## Loss106540665: higher receipts outweighed by higher spend

Our submission56081391 is seat0:75,560 versus76,091, a531 deficit. Ours earns3,385
more in sales but spends3,916 more:1,864 hiring,1,482 products,470 seeds and100
animals. This accounting does not by itself identify which investment was wrong.

The first cash difference is+28 at action1. The first material deficit is−358 at
168 because our400-coin strawberry investment occurs earlier. Installed animal
portfolios first differ at177. The first held-yield quantity difference is218
(WOOL8 versus4); an EGG key with zero quantity at177 is not counted as a yield
difference. The first unequal positive daily-production increment is at263.
Lifetime production differences are+45 MILK,+13 STRAWBERRY,+9 EGG and−52 WOOL.

The same observable SELL-prefix proposal is not universally helpful. At717 it
adds8 relative coins, but at718 it loses42: own−18 and rival+24. The six tested
turns were selected from the first loss and retained unchanged as exploratory
points on the second. Do not deploy a blanket sort from the positive529 witness.

## A concrete240-coin repair, with exact continuation checks

Both of our recorded paths buy17 WHEAT seeds at600 and9 at624 and finish with24
unused. At600 we already hold6. There are eight remaining WHEAT plantings:
609,610,611 twice,615,617,621,622. Thus two additional seeds suffice.

The offline replacement buys2 instead of17 at600 and0 instead of9 at624. Original
market positions remain intact; no other unit or market request changes. The
continuation carries cash/seed deltas rather than resetting the extra cash away.
Every one of119 transitions from600 through718 is re-audited and compared.
Both public replays contain engine seed metadata, so the final continuation also
checks all random-boundary farm and town fields, with no excluded boundaries.
That metadata is never supplied to a runtime policy.

Both comparisons preserve every nonfinancial field except the intended WHEAT
seed count and add240 own cash without changing rival cash. Terminal seeds fall
by24 to zero. Conditional final scores become96,235 versus96,979 (still−744) and
75,800 versus76,091 (still−291). These are recorded-action-path counterfactuals,
not games against responsive opponent programs, and neither is a demonstrated win.

ALDER is implementing the independent runtime demand calculation from its own
current and prefix-compatible alternative routes. The fixed replay indices in
this diagnostic are not a deployable seed-purchase rule. ALDER owns that policy,
its branch semantics and all independent development/held panels.

## Other candidates and negative controls

Each replay contains78 same-position HARVEST alternatives to truly inert unit
requests after the complete ordered worker phase. Only the first16 chronological
cases were retained for exact counterfactuals; every retained case has zero
immediate cash gain. Harvesting into a worker's inventory is not a sale, and an
earlier harvest may merely displace a later one. No production improvement follows
from these counts alone.

The28 manufactured official-engine tests include an underbuy that changes a
subsequent planting: the continuation stops with NONFINANCIAL_DIVERGENCE and
reports no gain. Corrupt baselines likewise cannot generate a claimed benefit.
No full-game seeds were consumed by this diagnostic component; no agent default,
Kaggle submission, transport-owner file or peer policy path was changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
