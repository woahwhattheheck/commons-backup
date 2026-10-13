# INTEGRATION-SPEC — `r04_melon_cap`

Source-only, default-OFF repair. Keep the existing key `r04_melon_cap`; do not
mint a sibling controller.

The guard is a **committed-production** cap, not a sold-only cap. Before any new
MELON proposal is admitted it reserves: conservative sold units, MELON already
held in shed/worker inventories, and six units for every live own MELON tile.
Malformed custody fails closed for MELON while non-MELON proposals pass through.

FourthQuadrant proposals are mutually exclusive alternatives: admission returns
one supplied proposal or `None`. For every MELON alternative, require unique
outer `tiles`, exactly one canonical MELON seed per selected tile, and every
`variants[*].bundle.lots[*]` record to bind the same tile set through its exact
`plant_step` and 1-based `worker` back to an exact `PLANT MELON` action in that
route's `variants[*].patches` program.

Lot membership is not sufficient by itself. Scan the complete patched farmer +
hand action surface using the engine's semantic PLANT prefix and require that the
set of executable MELON-PLANT `(step, actor)` identities is **exactly** the lot
identity set. Thus an extra farmer/hand PLANT, including an extended
`["PLANT","MELON", ...]` row, fails closed rather than hiding behind valid lots.

Also bind the producer's first-day market custody from
`variants[*].bundle.land.{step,slot}`. The entire appended suffix at that row
must be exactly:

`BUY_LAND`, `BUY_SEED MELON <seed_units>`, then `workers` literal `HIRE` rows.

For canonical FourthQuadrant MELON there is one planting cycle, so
`seed_units == len(tiles)`. This blocks both mismatched seed quantity and a
self-consistent metadata+overspend forgery. All route variants must satisfy the
same contract.

Keep the original proposal object unchanged only when the whole executable
commitment fits the current reserve. Never shallow-shrink metadata and never
consume reserve merely by inspecting another alternative.

`MELON_LIFETIME_UNIT_CAP = 28` is deliberately conservative and is not claimed
to equal the exact number of full-season town-center consumption ticks.

Hook only when `configuration.get("r04_melon_cap") is True`, at the one canonical
proposal seam. OFF identity, current-native engagement, economics, and graph
composition remain separate gates before activation.
