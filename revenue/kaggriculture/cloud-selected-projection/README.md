# Selected-action stock projection

`projection.project_selected` supplies the generic SELL transform with current
post-unit stock and an ordered, lossless continuation. It calls no production
controller. Runtime requirements are Python's standard library and the existing
standalone `cloud-execution-lab/mechanics.py` from official engine
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

## Use

```python
from copy import deepcopy
import mechanics
from projection import project_selected
from selected_action_sell import SelectedActionSell

# Obtain the authoritative action once, outside this helper. Future actions
# must come from that same selected continuation, not a second baseline agent.
packet = project_selected(
    mechanics, observation, configuration, selected_action,
    future_actions=known_selected_actions_by_absolute_step,
    end_step=known_end_step,
    contingent_harvests=(),
)

post = deepcopy(observation)
seat = post["player"]
post["farms"][seat] = packet["post_units"]["farm"]
post["private"] = packet["post_units"]["private"]
# Build the producer commitment contract against this post-unit state.
# It must refer to the same selected action and actual committed errands.

seller = SelectedActionSell()  # Retain one per match for its public history.
result = seller.transform(
    observation, configuration, selected_action,
    post_unit_shed=packet["post_unit_shed"],
    projection=packet["projection"],
    arrival_contract=current_arrival_contract,
    reservations=caller_operating_reservations,
    fallback_action=valid_selected_fallback,
)
```

The producer reads only the selected player's farm/private state. It needs no
rival-private state, environment seed, replay future, network, or model call.
The generic SELL module separately reads public rival observations. Neither
helper calls or advances the authoritative production controller.

## Meaning of the projection

Current worker actions are executed once on copied state at the actual shed
capacity. Already discarded current stock is not recoverable by a later sale.
`post_unit_shed` contains that actual current result; current unit changes are
not emitted again as future stock events.

Future unit actions use a **lossless conditional shadow**. A requested ten-unit
DROP remains a ten-unit event even when the reference schedule has room for
only one. Events retain farmer/hand order and inventory insertion order.
PICKUP withdrawals and PLACE deposits retain their actual operation and worker
metadata. EOD deposits are after market, in worker/inventory order. Market
BUY/SELL effects appear only in `future_market`, not again in `stock_events`.

Every valid future acquisition is assumed fully funded and admitted. This is
not a cash, quote, or actual fill forecast: `future_cash_forecast` is explicitly
null. The SELL consumer must independently certify the same full orders using
its cash/capacity checks. In particular, this producer supplies **no product-buy
cost bound**; paired-rival funding bounds remain the caller's responsibility.
Only a certified lossless continuation is eligible for optimization. A shadow
state can exceed capacity; that is an obligation to resolve, not a claim that
the engine permits the overflow.

The horizon ends at the earliest of the requested end, eight future decisions,
the first daily boundary, the final decision, or a missing future action.
A stock-clamped future PICKUP also ends the usable prefix before that action:
its accidental baseline fill could change when an earlier SELL changes. No
missing action becomes an invented PASS. Ending at the first EOD permits the
known deposit but avoids simulating later actions against unknown weeds or
new shops. In the standard720-state game there is no invented action719 or
final stock liquidation. A shorter horizon is a conditional planning window,
not a claim that the match ends there.

`phases` contains diagnostic conditional private-state snapshots, not predicted
cash. Inputs remain unchanged. `diagnostics.end_reason` explains truncation.
Caller selections, production plans, operating reservations and fallback remain
outside this component.

## Pending producer lots

A selected future HARVEST ordinarily contributes its conditional physical stock
projection. When the same unrealized harvest is instead covered by a separate
committed-capacity contract, explicitly pass its `(absolute_step, worker_index)`
in `contingent_harvests`. The helper executes the harvest's tile effect but does
not credit its newly collected units to guaranteed carried stock. It preserves
all previously observed carried goods. Later duplicate harvests therefore do
not manufacture another lot. The fresh caller contract still reserves the
whole pending lot; it does not increase saleable stock.

The caller must align these exclusions with its actual committed plan and
contract. This helper does not infer errands from opportunities, pick target
workers, invent guaranteed output, or synthesize commitment identities. Do not
represent one unrealized lot as both positive projected stock and a pending
capacity event. Missing/rejected commitments are not silently promoted here.

## Ordered consumer repair

The accompanying change to `ProjectionLedger.feasible` checks physical stock
bounds after each ordered event, rather than only after summing a whole phase.
A later PICKUP cannot repair an earlier spilled DROP, and a later deposit cannot
fund an earlier withdrawal. Existing phase-end stock minima, pending capacity,
cash checks, market positions and optimizer function bodies stay unchanged.

Deterministic witness: WHEAT90+CARROT10 fills the shed. On the next turn the
farmer drops MILK10 before a hand picks up WHEAT10. The original transform
selects CARROT SELL1, so the official interpreter discards nine milk. The repair
retains SELL10 and all ten milk. Reversing the workers' transfer order still
permits a delayed sale; this is not blanket liquidation. These are synthetic
mechanics fixtures, not measured game wins.

## Reproduce

Use an existing cloud engine cache, such as artifact10005621438, and the existing
source/evaluator tree. No preparation download or new game run is required.

```sh
D=revenue/kaggriculture/cloud-selected-projection
python "$D/test_projection.py" --engine-cache /path/to/engine --report result.json -v

# The original seller interface suite is retained unchanged.
cd revenue/kaggriculture/cloud-execution-lab
python -m unittest test_selected_action_sell -v
```

For the preserved lab evaluator layout, additionally pass
`--evaluator ../cloud-execution-lab/reference/evaluator/evaluate.py` and
`--engine-loader ../cloud-execution-lab/reference/evaluator/loader.py`, using
paths relative to the working directory. `--seller` can select an exact source
file for a distinguishing baseline check.

Local execution:21 tests pass, including144 independent fixture cases and378
full-interpreter transitions across both seats. Restoring exact original seller
SHA256`9fac22b0212989259b92f628e4f594f1ec56565581c90e95b910c59af5a20307`
makes two ordering tests fail; the other19 pass. `results.json` binds the actual
source and engine bytes. No new full games, held seeds, benchmark promotion,
competition upload, or hosted rating claim belongs to this component.

## Attribution

New bridge/tests: ATLAS. Existing SELL callable, scenario optimizer and its
frozen standalone scheduler retain their original authorship. The four-line
ordering repair does not change their receipt mathematics or prior panels.
Official unit, harvest, construction, hiring and daily mechanics are injected
from Kaggle's Apache-2.0 source; the standalone extraction remains in its
existing file. Preserve its `reference/engine/LICENSE`, the lab's notices, and
all original source attribution when packaging this helper with those modules.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
