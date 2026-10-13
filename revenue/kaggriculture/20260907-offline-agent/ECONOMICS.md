# Economic policy comparison — 2026-09-07

The promoted standalone is `main.py`; the original45/48 incumbent is preserved
byte-for-byte as `incumbent_20260907.py`. No original logic was removed.
All candidates use the same public observations and unmodified pinned official
interpreter as the incumbent. No runtime network calls, external data or model
service. This is not Kaggle-hosted evaluation.

## Development comparison

[Run34082876909](https://github.com/woahwhattheheck/commons/actions/runs/34082876909)
used seeds37,211,997 in both seats and compared four preselected hypotheses
against the unchanged incumbent and its compact22-animal opponent:

| Candidate | Versus incumbent | Versus compact22 |
|---|---:|---:|
| Lifetime marginal-price economics | 1/6 wins, mean margin-14,343 | 4/6 wins, mean margin-3,463 |
| Capacity28, maximum10hands | 6/6 wins, mean margin+4,088 | 6/6 wins, mean margin+2,216 |
| Forecast horizon20days | 1/6 wins, mean margin-8,972 | 0/6 wins, mean margin-17,750 |
| Complete more same-tile tasks | 1/6 wins, mean margin-1,571 | 0/6 wins, mean margin-4,915 |

Only the capacity candidate advances to the separately declared holdout set:
23,83,449,2027,65537, both seats. This choice was made before viewing those
results. Failed variants remain reproducible in `candidate.py` and `compare.py`;
they are not promoted merely because the added logic appears sophisticated.

## Why these candidates

The original three losses retained36animals and ended with zero inventory,
so they were not agent crashes, herd disappearance or failure to liquidate.
For example, seed37seat0 expanded from19 to36animals around days10–13,
made4,051 movement actions versus compact22's2,888, and finished5,045coins
behind. It was about9,820coins behind at day15. Seed37seat1 lost3,060 and
seed997seat0 lost172. These observations motivate reducing the marginal
land/labor burden, but do not themselves establish causation. Paired candidate
tests supply the intervention evidence; holdouts test whether the change
extends beyond the failure examples.

Instrumented comparisons record market-order pressure, unfed-without-buy
turns and daily prices/land/cash. Those counters are diagnostic, not automatic
proof that an order was dropped: affordability, ending rules and resource
state also matter.

## Independent holdout result and promotion

[Run34083074614](https://github.com/woahwhattheheck/commons/actions/runs/34083074614)
evaluated only the selected capacity28/max10hands policy on the five reserved
seeds in both seats. Against the unchanged incumbent it won10/10, mean margin
+6,454.1coins, minimum margin+4,012. Against compact22 it won4/10 and lost6/10,
mean margin-61.9coins, minimum-3,383. This supports improvement over the incumbent,
not dominance over every opponent. Across development and holdout comparisons
the selected candidate beat the incumbent16/16, and compact22 in10/16.

Promotion changes only the animal ceiling36→28 and maximum daily hands11→10.
It keeps expansion, crop choices, feed routing, original price horizon and
market logic. Failed experimental branches are not in the submitted standalone.
The frozen incumbent remains runnable; `evaluate.py` now explicitly uses it
for policy-ablation opponents so the original comparison is not weakened by
quietly changing both participants. The tests check byte-identical incumbent
preservation and full-game action equivalence between the selected candidate
and the standalone.

## Order-pressure finding

In all12 capacity development games both agents reached the10-order cap on22
turns, but unfed-without-buy diagnostic counts were0. That does not prove every
possible order state safe; it does mean missing-feed orders were not observed
as the cause of these losses, and no unmeasured ordering patch was made.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
