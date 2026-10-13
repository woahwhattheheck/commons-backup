# Route-aware cap: held confirmation, seeds 9810101 / 9810119

Source frozen before these seeds ran (`results/routeaware-candidate-frozen.txt`).
Both seeds checked unused across every result, script and record of this lane
first. Both seats, versus intact Arlene and versus Apex, paired.

| | control | candidate |
|---|---|---|
| pairs | 8 | 8 |
| **W/T/L** | **4/4/0** | **8/0/0** |
| flips | | **4, every one T → W** |
| pairs worse on own cash or margin | | **0** |

mean d_own +100.8, mean d_margin +100.8, RNG path identical in all eight pairs.
88 fills with 108 errands dropped as already covered by the incumbent route.

## Development, 9810001 / 9810019 / 9810037

| arm | control | candidate | flips | d_own | worse | fills |
|---|---|---|---|---:|---:|---:|
| frozen cap | 7/4/1 | 11/0/1 | 4 T→W | +87.8 | 0 | 220 |
| route-aware cap | 7/4/1 | 11/0/1 | 4 T→W | +87.8 | 0 | **121** |

Identical paired outcome on every one of the twelve pairs, with 201 errands
dropped as route-covered. The same economic result for 45% fewer interventions is
the property composition needs: what cost T08's composed arm its held game was
perturbation, not the gain.

## Why fewer interventions is the point

T08's composed held failure, seed 9780119 seat 0 versus Arlene, is the SELL choice
reacting to changed arrival timing. Whole game, both arms sold **1,552 units** --
not one more or fewer -- and the composition realised 112 less cash for them, 143
of it in five strawberries moved from a ~41 price day to a ~12 one. No base
harvest was displaced and no sale was suppressed.

Over intact Arlene rather than the composed stack, both cap arms **gain** +31 own
and +31 margin on that same seed. Cap alone helps there; the loss is the
interaction alone.

## Arrival facts for a downstream scheduler

`PlanOverlay.pending_arrivals(observation)` publishes what the observation cannot
show, because the units are still on a worker:

| field | meaning |
|---|---|
| `product`, `units_total` | what arrives and competes for shed capacity |
| `units_incremental` | how much is genuinely new, after the route-coverage test |
| `arrival_step`, `arrival_kind` | when it lands; `eod_auto` for a one-way errand |
| `no_forced_sale_date` | always true — nothing expires these units |
| `route_harvests_it_today` | whether the incumbent collects that tile itself |
| `shed_room_now`, `competes_for_capacity` | the capacity question, stated exactly |

`no_forced_sale_date` is the field that addresses the measured failure: cap-rescued
units have no deadline, and liquidating them at the first opportunity is a choice
with a price.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
