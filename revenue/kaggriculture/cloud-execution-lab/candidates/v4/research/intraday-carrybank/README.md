# Intraday Carrybank (ASTRA-CARRYBANK)

Research-only, default-OFF evidence package inside the sole canonical TITAN V4 tree.
It tests one narrow mechanism: use an otherwise-idle actor already at SHED to move
same-day-consumable WHEAT or FERTILIZER from the capacity-limited shed into that
actor's uncapped carried inventory, freeing room before planned productive shed
inflow.

## Source authority

Official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.
`audit_engine.py` fails closed if that blob drifts.

The source audit establishes:

- `PICKUP item qty` accepts a quantity and subtracts that quantity from SHED.
- carried inventory `_inv_add` has no inventory-capacity guard.
- `FEED` consumes one carried `WHEAT`; `FERTILIZE` consumes one carried
  `FERTILIZER`.
- `HARVEST` and `COLLECT_FERTILIZER` write directly into SHED and require room.
- seeds are tracked separately from SHED, so seed hoisting is not this mechanism.
- manual `DROP` is lossy: the engine removes the requested carried quantity but
  places only `min(quantity, room)` into SHED.
- end-of-day inventory return is also lossy: only the amount that fits is restored,
  then the carried entry is deleted.

The last two facts make generic backpacking unsafe. A hoist must be consumed before
EOD; it cannot rely on DROP or automatic EOD return for safety.

## Admission rule

`carrybank.admit_carrybank_pickup(...)` emits a multi-quantity `PICKUP` only when all
of these are true:

1. The actor's current unit action is `PASS`; CARRYBANK never displaces productive
   work.
2. The actor is already adjacent to SHED; the proposal spends no movement action.
3. CAPTRACE/current projection reports positive shed pressure:
   `projected_inflow > current_room`.
4. The item is WHEAT or FERTILIZER only.
5. The same actor's supplied remaining same-day continuation contains enough
   `FEED`/`FERTILIZE` sinks, after subtracting inventory it already carries.
6. Quantity is bounded by all three of: shed availability, projected capacity
   pressure, and additional same-day sink demand.

If any proof input is missing or malformed, the helper returns `None`.

## Intended V4 seam

This is not a controller, scheduler fork, or new key family. The intended composition
is a tiny optional admission step beside the existing CAPTRACE capacity projection:
CAPTRACE supplies `projected_shed_inflow_units`; the selected scheduler supplies an
actor-local continuation truncated to the remaining callbacks in the current day.
The helper may replace only a currently selected PASS.

Because current TITAN replans online, this package is **not runtime-authorized** yet.
A production composer must either preserve the proved actor continuation or carry a
sticky consumption obligation forward across replans. Until that exists and passes a
paired economic gate, this remains research/default-OFF.

The existing B7 shed-overflow guard remains complementary and authoritative for
capacity-safe `DROP`; CARRYBANK does not replace it.

## Tests

From `revenue/kaggriculture/cloud-execution-lab`:

```bash
python -B candidates/v4/research/intraday-carrybank/test_carrybank.py
python -O -B candidates/v4/research/intraday-carrybank/test_carrybank.py
python -B candidates/v4/research/intraday-carrybank/audit_engine.py
```

The helper suite covers productive-action displacement, SHED adjacency, zero-pressure
rejection, existing carried stock, WHEAT/FERT sinks, non-consumable product rejection,
pressure clamping, same-day horizon clamping, malformed-plan fail-closed behavior, and
multi-quantity pickup.

## Next economic gate

Wire only through the canonical V4 selected scheduler/CAPTRACE stack and measure:

- prevented capacity-blocked HARVEST/COLLECT events;
- additional productive units captured;
- extra PICKUP actions and any displaced route/service work;
- feed/fertilizer starvation deltas;
- carried inventory remaining at EOD (must be zero for admitted hoists);
- terminal own/rival margin on both seats against current native opponents.

Promotion criterion: positive paired economics with zero lossy DROP/EOD incidents.
Mechanism feasibility alone is not a promotion verdict.
