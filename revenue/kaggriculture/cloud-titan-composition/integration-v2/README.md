# Producer arrival contract

Additive T08 interface work. Frozen selected SELL and all earlier branches remain
unchanged. This module contains no controller, optimizer, quote function or
simulation. It consumes current producer-owned plan facts, then emits contingent
capacity obligations and shared worker/target reservations.

```python
from arrival_contract import build_arrival_contract, pending_capacity

contract = build_arrival_contract(obs, cfg, selected_action, producer_snapshots)
extra_after_market = pending_capacity(contract, day_close_step, 'after_market')
```

Each producer supplies a complete snapshot for the current observation step:
`owner`, `observed_step`, and `plans`. Each plan supplies:

| Field | Contract |
|---|---|
| `errand_id` | Stable within producer; no duplicate IDs |
| `worker_index` | Farmer 0, hands 1 onward; exclusive while pending/carried |
| `target` | Observed board coordinates, exclusive while pending |
| `product` | Actual harvested product |
| `units_total` | Whole harvest competing for shed capacity |
| `units_incremental` | Genuinely incremental units; never substituted for capacity |
| `arrival_step`, `arrival_kind` | Producer's committed plan date; `eod_auto` or `worker_deposit` |
| `status` | `pending`, `carried`, or `aborted` |
| `observed_carried_units` | Producer-attributed realized stock, bounded by actual current inventory |
| `no_forced_sale_date` | Must be true; arriving goods do not require an immediate sale |
| `hire_order_index` | Required for a worker still contingent on a selected HIRE order |
| `deposit_action` | Explicit DROP or selective PLACE for worker-deposit plans |

Pending reservation is `units_total - observed_carried_units`. Carried stock is
already in the observation and is returned separately; it must not be added to
capacity a second time. A carried worker remains reserved while its producer
still owns its PASS-until-EOD plan. Abort releases the pending obligation; any
actual stock remains in the observation. Stale producer snapshots, overdue plans,
double-booked workers/targets and over-attributed carried stock are rejected.
The caller retains its safe selected action when a contract is unavailable or
invalid. The module does not authorize or fund HIRE; it checks references to
orders the authoritative action already selected.

EOD events are AFTER market on the current day-close step. Their first possible
sale is the next step; final-day EOD output has no usable sale window. A worker
deposit needs an explicit planned DROP/PLACE, not merely a path to shed access.
A current-step deposit must occur in the selected unit action. Future action
feasibility and stock attribution remain the producer's responsibility; this
interface cannot prove a false producer claim true.

Outputs include no sale lots, guaranteed future stock, prices, probabilities or
opponent data. Whole pending harvests remain contingent on successful execution.
The next SELL adapter must distinguish these obligations from observed post-unit
shed stock and must replan/cancel obligations on subsequent observations.

## Source and review boundary

Mechanics source: bundled exact Kaggle engine at
28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c, `_apply_unit_action` (MOVE/PASS do not
deposit; DROP and shed PLACE explicitly do). Producer sources: Claude cap
d39b989f842db7c51d06396998b0ccaea09cc305 and FLORA lost-production
46482481f5cec7fb1aa5165e89520f2240a0286b, `_eh_choose` and `_eh_action`.
FLORA's capacity requirement is `harvest_units`, while its valuation uses
`economic_units`; its held goods PASS until EOD.

Current contract follows root's T08 review at Slack1788809693.051589 and Claude's
proposed errand interface at1788809585.830569. Claude owns deposit/valuation
correction; this code does not duplicate it. Six synthetic interface tests cover
whole crop harvest, EOD phase, partial/full realization, abort, shared ownership,
stale inputs, contingent HIRE and final sale windows. These are not retained
midgame cap-plan replay evidence. That actual producer fixture was requested and
is still needed before a corrected integration panel. No new full games have
run for this contract. The generic author SELL API and corrected producer source
will be consumed additively when callable, with fresh unused dev/held seeds.

## Exact FLORA bridge

`FloraBridge(base_owner)` loads the unchanged admitted FLORA candidate, binds its
route reference to the real authoritative base, and replaces only its parent
callback with the already-selected action. It constructs no additional Arlene
instance. `transform(obs, selected_action, blocked_targets=...)` consumes that
action once; `owned_workers(obs)` lets other unit overlays exclude FLORA's leased
hands before they act. Do not compose an overlay that ignores those leases.

`producer_snapshot(post_unit_obs, selected_action)` exports actual FLORA rows to
the common contract. The caller supplies the exact own post-unit state if SELL
is also using post-unit stock. Mixing pre-unit obligations and post-unit stock
can double-count a harvest completed this turn. Once the dedicated hand carries
the product, the exact executor PASSes; the bridge cancels any unharvested
remainder of the originally planned quantity. Whole observed cargo is separate
from the producer's conditional `economic_units` valuation.

Three additional tests execute the unchanged FLORA callback and pinned unit
transition on explicitly synthetic midgame states: selected-action consumption,
HARVEST into carried stock followed by PASS, target disappearance/abort, and
partial harvest with cancelled remainder. Nine focused tests pass in total.
This remains separate from the requested retained actual cap-plan fixture.

## Raw-file packaging

`titan-selected-raw.tar.gz` is an additive variant of the accepted selected
archive. Only `main.py` changes; all 37 other members remain byte-identical.
The lazy shim resolves the retained file loader's `configuration['__raw_path__']`
before importing the unchanged SELL module. Normal imported-module loading uses
`__file__` as usual. The original archive is preserved.

`python build_raw.py` reproduces the variant. raw-archive-receipt.json records its
hash and two retained-observation parity cases through the actual pinned
`cloud-pack/official.py::make_agent` file loader. This is a targeted packaging
check, not another SIGNAL historical replay or a full game. No policy changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
