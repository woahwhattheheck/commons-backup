# Spatial producer component

`spatial_tempo.py` is a component of the existing TITAN controller. It does not
construct another producer or seller. The canonical integration owner retains
entrypoint, feature configuration, runtime guard and archive publication.

Consumer contract:

1. Create one `SpatialTempo(mechanics, pathing=..., tempo=...)` per TitanAgent.
2. After controller initialization or reconstruction, call `install(controller)`
   on the same retained component. Keep the existing production/consumer owners.
3. Apply `configure(configuration)` before production. Call the original
   TitanAgent action exactly once, then `finish(observation, returned_action)`
   after its runtime guard has returned, including deadline fallback returns.
4. Preserve the component across reconstruction; create a fresh component for
   a fresh match. Selected SELL reads that controller's current route.

The component retains only the player's observations and the producer's own
commitments. Recorded opponent actions are evaluation evidence only. Existing
package licenses and notices remain required. Private validation and complete
successful/failed game records are delivered through the existing project road;
they are not bundled into this source directory.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
