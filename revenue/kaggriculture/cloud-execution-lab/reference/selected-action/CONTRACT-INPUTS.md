# Selected-action SELL input sources

These are immutable targeted reference copies, read without running new games.
`UPSTREAM.json` records original paths, commits, byte counts and SHA-256 values.
The frozen standalone SELL scheduler and its completed panels are unchanged.

## Pins

- T08 contract and FLORA bridge: `021c0e60cc2af15a6606e51caddb870d1f680482`.
  `arrival_contract.py` SHA-256 `2ebe366f326ce1ff8a9a014f1a8142883a9393f69ae0aef00e203643e068ebd8`;
  `flora_bridge.py` SHA-256 `bcd4d893583bd8f45ddbf51d553b4a6d8b2a7c114e81dfe774ebed91134e6a58`.
- Claude committed producer: `1cd98ab36c5d2a5a5ab95e64607e1eacb055687f`.
  `arlene_plan.py` SHA-256 `ae92730c733d39eeff4ec4c6624f30e042f1a5b3b330874c8022f0627510a658`.
- Claude fixed-state ablation: `39e439aced4406bc538bd361e9627f9e1c0a4254`.
  `envelope-binding-case-669.json` SHA-256 `c36386c24f965cebb6f356003aab8080bcdccef9a7e892ffdd2be1ebbc0ae0e0`.

## Producer and caller boundary

`PlanOverlay.act(obs, selected_action=None, excluded_workers=(), blocked_targets=())`
accepts the action selected by the one authoritative controller. Its separate
`producer_snapshot(obs, selected_action=None, owner="cloud-model-lab-cap")`
reports committed errands. `opportunity_facts(obs)` reports candidate
opportunities and must never be reserved. `pending_arrivals` now raises rather
than exporting that candidate list under a misleading name.

Each snapshot has `owner`, absolute `observed_step`, and `plans`. A plan has a
stable `errand_id`, `worker_index` (farmer is zero), target coordinate, product,
whole `units_total`, separate `units_incremental`, `arrival_step`,
`arrival_kind`, `no_forced_sale_date: true`, lifecycle `status`, and
`observed_carried_units`. Only pending quantity that has not been realized is a
new capacity obligation. An aborted plan releases its pending reservation;
already carried stock remains physical inventory. Carried one-way errands keep
their worker until day close. The following day's snapshot removes that row.

`FloraBridge(base_owner).transform(obs, selected_action, blocked_targets=...)`
similarly consumes one supplied action. Its snapshot should be requested with
the caller's exact post-unit observation. A partial actual FLORA harvest cancels
the unharvested remainder because its worker then PASSes. Whole harvest units,
not the incremental economics units, occupy the shed.

The generic SELL transform must construct or call no parent. Current inventory,
conditional continuation projection, and operating stock/cash/market
reservations belong to its caller. Without a valid caller projection it returns
the supplied valid fallback. The old T08 adapter's proxy of `owner.R`/`owner.cur`
and `possible_extra_deposits` are historical comparison code, not authoritative
projections for changed production routes.

## Validated capacity contract

`build_arrival_contract(obs, cfg, selected_action, snapshots)` returns
`capacity_events`, `realized_carried`, `worker_reservations`, and `aborted`.
Contract snapshots and current post-unit stock must refer to the same state.
The version in this pin reads `obs['step']`; T08 owns normalization for seat 1
using day and hour when that field is absent. The generic transform can resolve
absolute step directly without editing the reference.

Each capacity event contains `owner`, `errand_id`, `worker_index`, `target`,
`product`, `step`, `phase`, `pending_capacity_units`, `units_total`,
`units_incremental`, `contingent: true`, `guaranteed_stock_units: 0`,
`no_forced_sale_date: true`, `first_possible_sale_step`, and
`sale_window_available`. These are feasibility obligations. They create no
guaranteed sale lot or revenue.

- `eod_auto` is this day's close at `(day + 1) * turnsPerDay - 1`,
  **after market**. First possible sale is the next step.
- `worker_deposit` is **before market**, requires an explicit planned DROP or
  PLACE, and if dated now must match the selected unit action. Travel alone is
  insufficient evidence of a deposit.
- `pending_capacity_units = units_total - observed_carried_units`.
  `realized_carried` is marked `already_in_observation: true`; the caller
  handles it once in its physical projection rather than adding it again.
- `pending_capacity(contract, step, phase)` accumulates dated capacity events:
  before-market events apply before and after that market; after-market events
  apply only after it. Last decision is 718 for a 720-state engine, so EOD719
  output has no sale window.
- Stale snapshots, duplicate owner/errand IDs, worker/target conflicts,
  over-attributed observed stock and unbound contingent HIRE slots are rejected.
  Such invalid inputs require the valid selected fallback.

## Retained development case 669

The committed fixture is seed 9810001, seat 0, step 669. Current shed contains
WHEAT 2 and STRAWBERRY 3; selected market is `SELL WHEAT 2`. One committed errand,
`cap-667-w8-t14`, has EGG 4 whole units / 2 incremental units due EOD671 after
market. It does not imply every reachable animal is a future deposit.

All historical ablation arms valued STRAWBERRY 3 at 552. Their selected engine
receipts were 90 for `none`, 90 for `coarse`, and 642 for `dated`, which appended
the strawberry sale. The binding change was feasibility, not sale valuation;
the immediate reserve of 91 was not itself binding. This is a retained local
mechanism case, not a new panel or a promotion claim. A committed-only generic
projection need not imitate a historical speculative envelope's exact timing.

The six-frame `cap-midgame-errand.json` has both pre-unit and post-unit states.
At step671 the pre-unit snapshot is pending EGG4; the post-unit snapshot is
carried EGG4. Its saved `arrival_contract` was built from the pre-unit snapshot.
Do not combine that contract blindly with its post-unit observation: build the
contract from the matching post-unit snapshot, where pending capacity is zero.
At672 the errand is absent following the automatic deposit.

## Attribution

T08 sources retain their SPDX MIT or Apache-2.0 declarations. The upstream root
Apache license is retained as `t08/LICENSE-ROOT`; full MIT text is present in
`claude/LICENSE-MIT.txt`. Claude's source handoff retains its own `LICENSE`
attribution and MIT OR CC-BY-4.0 grant; these reference copies use the MIT option.
Existing standalone scheduler attribution and license remain in the lab.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
