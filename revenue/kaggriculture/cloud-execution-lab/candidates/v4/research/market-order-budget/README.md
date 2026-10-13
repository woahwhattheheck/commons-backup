# TITAN V4 market-order execution budget — ASTRA-ORDERBUDGET

This package is an additive research/control-plane lane inside the **sole canonical** `main:candidates/v4` tree. It does not create a second router, controller, runtime, archive, feature key, or V4. Nothing here changes production behavior.

## Source-real seam

The pinned official Kaggriculture engine (`reference/engine/kaggriculture.py`, Git blob `3c202c7ee921da239356789e266b694635103fc4`) computes

```python
max_orders = max(1, int(get(env.configuration, "maxMarketOrdersPerTurn", 10)))
...
q = list(m) if isinstance(m, list) else []
queues.append(q[:max_orders])
```

before it parses or commits market orders. The default executable budget is therefore **10 raw market rows per callback**. A nonempty order authored at slot 10+ is silently unreachable. Empty rows beyond the cap are not themselves economic loss, but they prove that an append-only composer can write into a region the engine never reads.

The cap is **rows, not units**. After the raw prefix is selected, surviving BUY/SELL rows expand their quantity one unit at a time inside the engine's player-lockstep market loop. Rival orders at the same raw index participate in that lockstep before the interpreter advances to the next row. Therefore adjacent same-product rows are not automatically interchangeable with one consolidated multi-quantity row: consolidation can change rival interleaving, quotes/commits, first-failure behavior, and the position of atomic HIRE/BUY_LAND rows. ORDERBUDGET never treats quantity consolidation as a generic way to recover slots.

This is an integration risk rather than a new economics hypothesis: current V4 contains several independently owned market-producing transforms. Their policy/economic ownership stays where it is; ORDERBUDGET owns only the shared execution-budget boundary and evidence that composition stays within it.

## What this package does

`market_order_budget.py` classifies a returned action without changing it. It distinguishes structural overflow (`len(market) > cap`) from an actual nonempty dropped order, records the last active raw slot, and exposes `admission_slot()` as a planning-only primitive. That primitive returns either an existing empty row inside the executable prefix, the next append position when the queue is shorter than the cap, or `None`. It never compacts/reorders the parent queue. A returned slot is **capacity evidence only**: inserting a new economic order into that slot still belongs to the owning policy lane and must preserve that lane's timing/lockstep semantics.

`audit_authored_routes.py` authenticates the frozen `b567942e…` production archive and all manifest members, authenticates Arlene bytes, decodes all four 720-callback authored route tapes, and reports raw queue/headroom pressure for every callback. Authored intent is not a fill or economics claim.

`market_budget_native_entry.py` is a test-only fixture copied beside an authenticated runtime. It delegates to the unmodified native `main.py::agent`, records queue-budget telemetry, and returns the parent action unchanged. Telemetry failures are swallowed. `run_current_native_census.py` runs that wrapper against native self-play in both seats through the existing process-isolated official-interpreter runner. This is liveness/composition evidence, not a strength panel.

## Decision contract

The first falsifier is intentionally cheap. If authenticated authored/current-native output has no nonempty overflow, this package does **not** justify a runtime policy. A full queue with no admission slot is only a warning to future composers: they must not append another order without separately proving a safe replacement/rewrite under the owning lane's semantics.

If a nonempty slot-10+ witness appears, the next step is to identify the exact composing owner and replay the same callback through the official engine. ORDERBUDGET still does not choose which economic order should win. Any repair must preserve existing row indices unless the relevant policy owners explicitly gate a reorder. A proposed compressor additionally needs proof over both players' row partition, quantity expansion, atomic HIRE/BUY_LAND boundaries, first-failure behavior, quote/commit inventory, and the untouched raw tail; this package supplies no such compressor.

## Explicit non-overlap

- TOP-AGENT-MECHANICS owns replay/evidence ordering and raw-slot provenance, not engine queue-budget admission.
- SAME-TURN-FUNDING owns basket financing/rank inside its parked adapter. Its cap check remains authoritative for that adapter.
- V231/V233/E184 and other sale/acquisition lanes retain their policy, pricing, timing, and fill semantics.
- CARRYBANK retains shed-capacity/intraday inventory ownership.
- ORDERBUDGET adds no BUY/SELL/HIRE/LAND/animal/labor preference.

Slack custody: `#titan-kaggriculture` TS `1789186272.436169`.

## Reproduce focused source tests

From this directory:

```bash
python -B -m unittest -v test_market_order_budget
python -OB -m unittest -v test_market_order_budget
python -B -m py_compile market_order_budget.py audit_authored_routes.py market_budget_native_entry.py run_current_native_census.py test_market_order_budget.py
```

The dedicated workflow additionally pins the official engine Git blob, authenticates artifact `10180428228` / ZIP SHA256 `737c0b2b…` / inner archive SHA256 `b567942e…`, runs the authored-route census, and runs one fixed-seed native self-play census in both seats. Hosted results are not claimed until the exact-head run completes.
