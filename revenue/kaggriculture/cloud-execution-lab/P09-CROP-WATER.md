# P09 crop-water obligation policy

Operation: `op:titan-v25-orders-20260909-P09`

This additive policy turns public crop state into dated WATER obligations for the existing TITAN producer. It does not create a second controller and it does not change default gameplay by itself.

## Engine pin and semantics

Pinned Kaggriculture engine: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

The policy preserves these engine boundaries:

- A newly planted crop starts at `consecutive_unwatered = 1`; omitting WATER through that day's refresh kills it.
- A crop with `consecutive_unwatered >= 1` is therefore survival-critical today.
- A second WATER on the same day is a no-op.
- One-time crops gain yield immediately from WATER only in their crop-specific bonus window. Fertilizer changes that increment from +1 to +2, subject to the crop's yield cap.
- Ongoing crops receive their base scheduled production at daily refresh even if they were not watered. WATER has incremental production value only when the crop is fertilized on a due production refresh and there is room for the extra unit; the marginal effect is +1 over the unwatered base production.
- A non-critical, zero-marginal WATER is only *deferrable*, not free forever. `can_defer_water` requires an already-planned future WATER no later than the next survival deadline, or removal before that deadline.

## API

- `water_obligation(tile, specs, day)` → immutable reason-coded obligation.
- `rank_water_obligations(tiles, specs, day)` → survival-first deterministic contention ordering.
- `can_defer_water(..., next_water_day=..., removal_day=...)` → bounded route-level deferral check that never invents a future service.
- `classify_tiles(...)` → stable read-only logging/fixture representation.

Priority is lexicographic: survival first, then current marginal units, then the nearest survival deadline. Route ownership, travel feasibility, harvest timing, fertilizer allocation, and release decisions remain with the existing producer/P10/P11/P12 seams.

## Deliberate non-claims

This patch is a shared decision primitive plus focused semantics, not a playing-strength result. It does not claim freed-turn frequency, terminal-cash gain, W/T/L gain, or that any current route should be rewritten. Those claims require source-pinned matched complete games after a canonical writer composes the policy into an actual route edit.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
