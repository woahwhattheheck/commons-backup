# TITAN V5 lean-feed carry economics — post-merge source correction

Target: Commons merge `a590e578574e09995bea4bf8a5eaffa56cd72461` / PR #14345.

## Why the merged model cannot authorize economics

The official engine does not contain Corn/Pasture/Straw feed commodities. Every
animal `FEED` action consumes exactly one `WHEAT`. `BUY_PRODUCT` accepts only
`WHEAT` and `FERTILIZER`, and commodity purchases execute per unit in lockstep,
with each WHEAT unit quoted at the changing post-buy inventory. Therefore a fixed
Corn/Pasture/Straw reserve vector and `units * fixed_unit_price` simulation cannot
represent the active engine.

The retained current-lineage runtime is also not a generic `buy_feed()` policy.
`TitanAgent._feed_stock_selected()` consumes an already-selected `SELL WHEAT`
queue and calls `operating_stock.protect_feed_stock()`. That helper certifies a
bounded route/feed suffix and, only on a changed window, leaves its dynamic
`required_wheat`. It explicitly does not decide animal acquisition or estimate a
game cash gain.

## Fix-forward boundary

The source contract is now hard-pinned to WHEAT-only engine facts and the known
runtime/helper blobs. Exact D2 archive member bytes are not retained in this
carrier, so active D2 policy identity remains blocked. Until those bytes are
provided and safely authenticated, the public report conclusion is
`SOURCE_MODEL_BLOCKED`, all economic arrays are empty, and no candidate/promotion
is authorized.

Required evidence to reopen economics:

1. Exact D2 archive bytes matching `3d250d7b…` and a safe member manifest.
2. Exact active runtime/helper source identities from that archive.
3. A WHEAT-only public-state census of current SELL-reservation behavior.
4. Paired official-engine economics only if the census proves reachable excess.
