# Exact cycle conditions

Let P(I) be the official rounded unit quote at stock I. A BUY quotes P(I−1).
Both players quote before either commits the current unit. Quantities below
assume successful fills, adequate cash/storage and sales above the $1 floor.
Existing worker/input/stock/slot obligations must be preserved separately.

Our slot0 SELL q and slot1 BUY q, rival slot0 SELL r and no later same-product
order, yields:

* Own sale receipts: sum over j=0..q−1 of P(I+j+min(j,r)).
* Own repurchase cost: sum over j=0..q−1 of P(I+r+j).
* Rival cash difference versus our no-trade control: sum over j=0..r−1 of
  P(I+j+min(j,q))−P(I+j).

On the default nonincreasing curves, our cash difference is nonnegative and
the rival's is nonpositive. Strict benefit requires crossing rounding steps.
All inventory quantities and final market stock match the no-trade control.
For rival BUY r, replace the first min term by −min(j,r), use I−r+j for our
rebuy sequence, and compare rival costs P(I−j+min(j,q)−1) with P(I−j−1).
Our cash difference becomes nonpositive and rival savings nonnegative.
cycle_quotes.py computes these sums. Ninety-six quantity/rounding cases match
the pinned official market transitions.

At default WHEAT I10000, q=r=1, rival SELL: own sells25 then buys24, net+1;
rival gets25 in both worlds. Rival BUY instead: own net−1 with sufficient cash.
With initial own cash0, the latter rebuy cannot fill: cash+25 and one less
WHEAT is an ordinary sale, not a profitable closed cycle.

The rival's next slot matters. Rival SELL WHEAT1 then BUY WHEAT1 yields own+1,
rival+1 and zero immediate cash-margin gain. Rival cash0 SELL MILK1 then BUY
WHEAT1 yields own0, rival+1, margin−1. These identical-observation alternatives
explain the liquidity transform's flat-price condition. Its immediate own
cash/inventory restoration does not guarantee later relative-game outcomes.

## Floor stock and temporal consumption

Default FERT's first inventory with P(I)=1 is10493; P(10492)=2. Solo BUY q then
SELL q restores cash. With successful fills it removes min(q,max(I−10493,0))
market units, since a sale quoted1 adds no supply. Cash and empty shed space
bound fills. At11000, buying/selling100 removes100; cash3 removes3; full shed
removes0. There is no direct cash profit and FERT has no town consumption.

Paired flow changes the result. At FERT10500, own BUY100 then SELL100 while a
rival sells100 in slot0 produces own−92/rival+92/margin−184 relative to own
no-trade. With both players doing BUY100 then SELL100, each gains20 and the
immediate margin gain is0. Therefore floor state changes are measured and
preserved, but the runtime transform does not execute a floor cycle.

Temporal WHEAT example: I10000, buy1 for26; four visible BAKERY instances
consume four WHEAT after the market phase; next market sell1 for27. Net+1
with no opposing supply. Rival SELL5 in the acquisition turn changes own
result to−1. Known demand is therefore one term in the exposure calculation,
not a guaranteed profit or probability for unknown rival orders.

Production inputs remain reserved. The same worker cannot simultaneously
collect fertilizer, feed, care, harvest or move; a nominally free input still
uses a worker opportunity and later storage/order capacity. This component
preserves supplied unit actions and operating reservations. T05 retains
terminal collection; T12 retains observed-flow prediction; T08 owns promotion
and whole-agent composition. No alternate production controller is embedded.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
