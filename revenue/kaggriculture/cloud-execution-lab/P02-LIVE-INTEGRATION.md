# P02 live integration and official matched gate

Operation: `op:titan-v25-orders-20260909-P02-sol-helix-integration-01`

This additive packet consumes the bounded land-unlock timing certificate staged in
PR #11248. It does **not** change canonical `main.py`, `TITAN-CONFIG.json`, the
current release archive, or any existing route producer.

## Runtime ownership

`land_unlock_runtime.py` is a selected-action overlay. It calls no producer and
moves only one exact represented `BUY_LAND`:

- an advance emits the early order, waits for the next public observation to
  prove exactly one quadrant unlocked, then suppresses the represented original;
- a failed early fill leaves the original order untouched;
- a deferral removes the represented original only after a certificate names a
  later safe step, then re-certifies current cash, route, unit action, market
  slack, seed, first-water and terminal bounds at that target;
- route changes, route-decision checkpoints, active spatial/quadrant ownership,
  deadline fallbacks, ambiguous market rows and unsupported economics fail
  closed;
- repeated calls for the same engine step reproduce the same action mutation;
  backwards/step-zero streams clear pending state.

`p02_candidate.py` composes the overlay after the canonical completed-action
boundary. The unchanged canonical agent is the control in the hosted official
engine panel.

## Evidence contract

The workflow runs source/engine contracts and `build_integrated.py --check`, then
uses the repository's process-isolated official evaluator and exact pinned
Kaggriculture 1.32.7 engine bytes. Candidate and current control play both seats
on disjoint development and held-out seed banks. Public-action telemetry records
only the selected route ID, before/after market queues, state-machine reason and
receipt events; it does not serialize observations, private inventory or hidden
seeds.

No playing-strength, leaderboard or promotion claim exists until every scheduled
game is complete and the uploaded immutable panel is reviewed. A negative or
zero-activation panel leaves the packet additive and canonical defaults unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
