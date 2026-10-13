# E19 demand-aware reinvestment candidate

Operation: `titan-v25-orders-20260909-E19`

This lane adds a **pure economics interface**, not another agent. The current
producer remains responsible for authoring physical production alternatives,
and the existing funded-payback machinery remains responsible for funding and
route feasibility. The helper only answers: *given a funded producer-owned
alternative, what are its incremental sale receipts after its own expansion,
public rival supply, and deterministic public market absorption?*

## Why this is needed

The currently enabled annual crop-release admission in `cloud-execution-lab`
prices three CARROT units from the current quote with already-owned CARROT and a
fixed `+100` rival-supply stress. That is intentionally bounded, but it does not
model the deterministic unlocked-shop/town-center absorption that occurs during
the release's long maturation/outlet interval, nor sequential quote collapse
from the candidate's own added yield.

The canonical ECON funded-payback evaluator already establishes the relevant
ordering: market actions are processed first; then known currently unlocked
shops and town center absorb inventory. Unknown future shop unlocks are not
credited. `demand_aware_reinvestment.py` reuses that contract at a much smaller
producer-choice surface.

## Interface and ownership

- `forecast_marginal_receipts(...)` values only candidate-added units. It
  sequentially applies official SELL quotes, inserts either visible rival
  standing yield or a caller-supplied public seller forecast, and applies only
  deterministic demand from currently unlocked shops/town center.
- The preferred integration is to pass the existing frozen seller's public
  `SellScheduler.rival_supply(...)` result as `rival_supply_units`. That keeps
  recent-harvest inference seller-owned instead of creating a second ledger.
- `ProductionCandidate.costs` is intentionally explicit. The caller must include
  incremental land/prep, seed/animal, worker service, travel/operating inputs,
  harvest/deposit handling, and any other paid route obligation already proved
  by the producer/funded-payback layer.
- `choose_reinvestment(...)` is an explicit no-op when the inherited mix already
  has the highest executable positive marginal value.
- No future own/rival sale cash, hidden rival stock, replay data, future shop
  draw, or unknown demand is credited.

## Focused contracts

`python -m unittest -v test_demand_aware_reinvestment.py`

The focused suite covers: high current quote collapsing under own expansion;
modest quote supported by repeated known demand; visible crop and animal supply;
composition with the existing seller forecast; terminal non-payback; funding
rejection; inherited no-op; strictly-better choice; and market-before-town
ordering.

## Integration gate

This candidate is **not enabled in current TITAN** and does not modify the
canonical archive. The intended next patch is narrow: replace only the annual
crop-release static product-value screen with this forecast, fed by the existing
seller public-supply interface, while preserving the exact producer route,
actors, funding proof, crop receipts, operating-stock guards, and seller.
Activation still requires E19's matched official-engine complete-game gate (32
balanced seed/opponent pairs x both seats = 64 complete games per variant, then
holdout) and exact current-archive rebuild/readback. No playing-strength claim is
made by these focused contracts.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
