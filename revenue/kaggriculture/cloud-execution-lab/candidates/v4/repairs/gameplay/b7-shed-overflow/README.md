# B7 shed-overflow salvage custody

This directory preserves the exact durable B7 evidence carrier from PR #12562 inside the sole canonical V4 workspace. It is **not** an activation or economics verdict.

The B7 mechanism was left out of V4, but its latest V3.1 gate did not reject the mechanism: run `34592366181` stopped in the pre-spend freshness bind because the workflow pinned gameplay root `8e3d92a...` after live V3.1 advanced. Updating that SHA in place would be invalid because the intervening range changes gameplay bytes.

`legacy/` therefore carries the exact existing Git objects only: mechanism donor `a27da659...`, paired baseline/candidate wrappers `fea37735...` / `f5b9ea0a...`, and strict paired gate `37d5bb6c...`. The stale workflow is deliberately not copied.

Before any V4 wiring or default change, recompose the mechanism against literal current `main`, prove the current helper/package ancestry, and rerun the exact-cell paired gate. Preserve its conservative disposition: inactive => kill; any negative paired margin cell => hold; only active, zero-negative, positive-mean evidence may widen. Until then this pack is custody/provenance only.
