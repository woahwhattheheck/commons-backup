# CARRYBANK current-route safety closure

This follow-up consumes the post-merge CARRYBANK build demand without wiring a dead or unsafe runtime bridge.

The original helper counted future `FEED` / `FERTILIZE` actions as available sink capacity after subtracting only inventory already carried at admission time. That is insufficient for the current route tapes: the same continuation can itself acquire WHEAT or FERTILIZER before those sinks. An early hoist can therefore consume sink capacity already spoken for by a later `PICKUP`, `COLLECT_FERTILIZER`, or (for WHEAT) an unprojected `HARVEST`, leaving carried stock exposed to the exact lossy `DROP` / EOD return behavior CARRYBANK was designed to avoid.

The helper now debits those future acquisitions conservatively. It also truncates a guarantee at `DROP`; sinks after a lossy inventory boundary are not credited. WHEAT capacity becomes unprovable if a `HARVEST` occurs before the boundary unless a future composer supplies an item-level projection.

`current_route_census.py` binds Arlene Git blob `bdb9cf58148a3c7961c085f4902759537decabf6` and scans each route only to EOD or the next branch checkpoint. To make the falsifier stronger, the census assumes every structural candidate is already shed-adjacent, positive capacity pressure exists, WHEAT/FERTILIZER stock is available, and the actor starts with no carried input.

Result: **27 raw actor candidates across 25 route-step cells, 0 corrected-safe candidates.** The raw route therefore has no CARRYBANK admission justified from future tape alone under the corrected consumption contract.

Disposition: `NEEDS_STICKY_OBLIGATION_NO_RAW_ROUTE_ADMISSION`.

This does **not** falsify the engine mechanism. A future runtime composer may still unlock it by owning a sticky consumption obligation across replans (or supplying an exact post-transform acquisition/product projection), followed by the existing both-seat economic gate. It does mean the current merged helper must not be wired by simply handing it a raw same-day route suffix.
