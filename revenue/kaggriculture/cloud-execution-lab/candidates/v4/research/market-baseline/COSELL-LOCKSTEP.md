# COSELL lockstep market witness

`cosell_lockstep.py` is a **research-only** oracle for one official Kaggriculture market mechanic that is not covered by the existing COBUY witness: when both players have an executable `SELL` of the **same item in the same market-row slot**, `_process_market` quotes both active units from one shared pre-commit market state, then commits both, then refreshes prices. The second player therefore does not take an intra-pair quote penalty from the first player's same-round sale.

## Bound authority

The oracle pins both official interpreter inputs consumed at module load:

- `reference/engine/kaggriculture.py` Git blob `3c202c7ee921da239356789e266b694635103fc4`
- adjacent `kaggriculture.json` Git blob `b354d06b742fe48402513792253f1a5c29366b20`

Both files are captured once. The Python snapshot is compiled/executed from memory, and the authenticated JSON snapshot is served from memory when the engine opens its adjacent specification. The reported identities therefore describe the same bytes that execute.

## Counterfactual

For identical starting public inventory and identical terminal quantities, the oracle compares three **market-processor** worlds:

1. **aligned** — rival and TITAN sell the same item in market row 0, so their active units are quoted lockstep;
2. **misaligned same callback** — an engine-inert zero-quantity row occupies TITAN row 0, so the rival completes row 0 before TITAN row 1 inside the same `_process_market` call;
3. **sequential market-only** — the rival sale is processed by one `_process_market` call and TITAN's sale by a second immediately following `_process_market` call on the same world, with **no interpreter phases between them**.

The physical terminal state must be identical across these three deliberately market-only worlds. `simultaneous_gain_vs_sequential_market_only` is therefore a quote-order cash delta, not an inventory or quantity artifact. `misaligned_gain_vs_sequential_market_only` should be zero.

The third arm is **not** a claim about waiting until the next callback. The pinned official interpreter runs `_town_consume(env, state, step)` after every `_process_market`, then plant decay and, at day boundaries, EOD processing before the next callback. Town consumption mutates public inventory and refreshes prices. The exact-engine regression uses the step-0 town-center boundary to prove that inserting just this real inter-callback phase can change the second seller's revenue, so a sequential-market-only result must never be labeled as a next-callback result. A real wait comparison requires full interpreter replay.

For nonlinear glut curves the same-slot effect can be material over multiple shared units. The effect is especially worth measuring for `WOOL` and `MELON`, whose above-I0 curves are quadratic, but the oracle accepts every official market product and does not assume the sign or size of the effect in advance.

## Deliberate boundary

This package does **not** predict a rival's hidden current action, move a sell row, mutate a controller, add a runtime key, or authorize activation. A useful follow-on needs source-bound incidence evidence: canonical current-route coordinates and/or frozen replay coordinates where both executable same-item `SELL` units actually occupy the same market slot, followed by both-seat economics. A hypothetical collision is mechanism evidence only.

Malformed quantities, booleans masquerading as integers, unknown items, and quantities above the default physical shed capacity fail closed. Market-prefix/cap admission remains the responsibility of the caller supplying an actual executable collision coordinate.
