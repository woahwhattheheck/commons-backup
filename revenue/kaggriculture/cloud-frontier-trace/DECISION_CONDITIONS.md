# Observable conditions checked in episode106392861

This extends the actual-results checkpoint. `moments.py` reads original replay actions/state and replays all719 transitions again with within-turn tile instrumentation; every transition must reconcile before context is retained. It captures8 shop unlocks,585 planting/placement effects,60 seat-days of labor,2094 tomato/cow context records and126 same-tile task groups. Full records are in results/106392861/moments.json.gz. This is not a new candidate simulation or a model of the competitor's hidden policy.

## Shop demand and allocation

| First visible step | New shop | Tomato price | Strawberry price | Milk price |
|---:|---|---:|---:|---:|
| 72 | PIZZA_SHOP | 60 | 135 | 175 |
| 144 | FARMERS_MARKET | 63 | 141 | 203 |
| 216 | PIZZA_SHOP | 68 | 164 | 194 |
| 288 | ICE_CREAM_SHOP | 74 | 178 | 210 |
| 360 | BRUNCH_SPOT | 81 | 193 | 216 |
| 432 | ICE_CREAM_SHOP | 94 | 176 | 203 |
| 504 | PET_CAFE | 120 | 107 | 208 |
| 576 | YARN_STORE | 163 | 41 | 212 |

Leader's first tomato planting is step224, price68, after the second pizza copy becomes visible at216. Additional plantings at248/251 see71. The18 later plantings start391 (price84, strawberry191) and finish471 (tomato110, strawberry166). The step391 expansion precedes the432 ice-cream shop, which does not consume tomato. This separates actual timing from an incorrect story that every new shop directly triggered tomato expansion. Both players' trades and town consumption affect prices.

**Condition for FLORA to test:** count copies of shops consuming each product; combine their actual consumption cadence with current market inventory, its change since the last plan, own/opponent visible installed crop cohorts and the remaining event-to-sale horizon. At224 there are two pizza copies plus farmers market consuming tomato. A later tomato planting can have an8-day lead while strawberry needs10; it still needs maintenance, capacity and liquidation work. Do not use fixed10cow/9tomato counts or a universal price threshold from this single trajectory.

## Labor spending versus real throughput

| Episode measure | Leader | Opponent |
|---|---:|---:|
| Hires across daily resets | 287 | 278 |
| Hire spend | 7,120 | 5,086 |
| Available unit-action slots | 7,248 | 7,035 |
| Changed unit actions | 6,886 | 6,314 |
| Movement actions | 3,689 | 3,075 |
| Nonmovement effects | 3,197 | 3,239 |
| Changed / available | 95.01% | 89.75% |

The extra572 changed actions include614 additional moves and42 fewer nonmovement effects. Thus greater throughput is not itself evidence of more production per worker. Day19 leader spends609 for13 hires, using313 of319 slots (166 moves,147 nonmovement effects); opponent spends232 for11 hires,253 of275 slots (121 moves,132 nonmovement). Differences in gross sales also reflect previously installed capital and endogenous prices.

**Condition for FLORA/SORREL:** compare incremental Fibonacci hire cost against a feasible remaining-day queue with explicit travel, maintenance, collection, harvest and deposit actions; reserve the slots required by existing assets before buying new ones. Count blocked/duplicate actions separately from PASS. These observations suggest what to test, not the marginal return of an additional hire.

## Tomato event and cow cadence witnesses

Leader tomato at(0,5), planted day9: FERTILIZE401 covers through day18; WATER402 precedes refresh407 (held0→2), WATER418 precedes refresh431 (2→4), WATER443 then HARVEST444 clears4, refresh455 adds2, WATER463 and FERTILIZE464 precede refresh479 (2→4). It produced8 units over four daily refreshes while using two harvest-sized batches. Exact harvest of the last batch is retained in the complete context records. Do not require daily HARVEST when held capacity and future refresh permit batching.

**Condition:** next added yield would exceed capacity, or decay/terminal liquidation is approaching → prioritize harvest and return; otherwise batch where it saves travel without forfeiting a production event. Check WATER/FERTILIZE flags and the event's preceding care day. No future output is guaranteed if maintenance is missed.

Leader cow at(4,4), placed day0: before refresh191 it is fed+cared with pending bonus5 and held0; after refresh it holds6, pending1. FEED and CARE by different workers both succeed at193; HARVEST194 clears6. Refresh215 turns pending1→2 without milk. Refresh239 consumes pending2 to produce3, then preserves today's care as pending1. FEED→CARE241 and HARVEST242 repeat. This directly checks that same-day care does not enhance that same refresh's milk and that care can accumulate before the first production.

**Condition:** protect survival feed and feed on a production day that can consume pending care; schedule CARE when another realizable production event remains and the feed/labor/capacity plan supports it. Estimate added milk from actual pending bonus and held space, not a fixed daily care multiplier. The recorded cow has six-unit capacity, so additional pre-first-event care beyond available output space can have no immediate realized gain.

## Joint action scheduling

126 repeated-target groups are preserved with actual worker order and changed flags. Leader's successful groups include36 FEED→CARE,17 CARE→COLLECT_FERTILIZER,16 COLLECT_FERTILIZER→HARVEST and a four-operation CARE→COLLECT_FERTILIZER→FEED→HARVEST group. Blanket same-tile exclusion would destroy valid complementary tasks.

Opponent WATER→WATER groups at136 and188 both fail because neither request changes the already-observed state; at453 and478 the first WATER succeeds and the second fails. This is both an initial-state precondition problem and a joint-reservation problem, not only duplicated coordinates. Joint PLANT seed demand must also be checked before execution; the interpreter converts oversubscribed same-crop requests to PASS.

**Condition:** reserve mutable effects (watered/fed/cared/collected/held yield, carried resources and seed counts) in actual farmer-then-hand order, allowing distinct complementary effects at the same coordinate. Update virtual state after each accepted task. LARK can use the original public frames at193,453,478 and their expected changed flags as offline regression inputs; candidate decision quality still requires new games owned by the active policy/model lanes.

The decision cases contain raw before/after frame observations and actions for exact witness steps. They are public replay data, never competitor executable code. All source hashes and original compressed bytes remain in the previous manifest. No account/submission action, universal-policy claim or hidden-intent claim is made.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
