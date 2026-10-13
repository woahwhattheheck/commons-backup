# W10 event-to-trace compiler

`event_trace_builder.py` is the narrow instrumentation bridge between a live producer/evaluator and the W10 certificate. Instead of hand-authoring cumulative snapshots, an adapter records observed per-tick deltas and absolute carry/shed gauges. The compiler deterministically accumulates those events, coalesces events from the same tick, carries the final state to the exact comparison horizon, and submits the resulting trace to the same strict validator used by `realized_fertilizer.py`.

It does **not** choose actions, forecast fertilizer value, change the producer, or claim that an event occurred. The adapter is responsible for recording truthful engine observations.

## Event-stream document

```json
{
  "schema": "titan.w10.realized-fertilizer-events/v1",
  "variant": "fertilized",
  "policy_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "identity": {
    "engine_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "evaluator_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "opponent_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "start_state_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "counterfactual_protocol_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "protected_commitments_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    "seed": 718,
    "controlled_player": 0,
    "horizon_tick": 10,
    "worker_tick_budget": 20,
    "product": "WHEAT"
  },
  "capacity": {"carry_units": 2, "shed_units": 4},
  "initial_snapshot": {
    "tick": 0,
    "fertilizer_actions": 0,
    "produced_units": 0,
    "harvested_units": 0,
    "deposited_units": 0,
    "sold_units": 0,
    "cash": 50,
    "discarded_units": 0,
    "worker_ticks_used": 0,
    "travel_steps": 0,
    "watering_actions": 0,
    "harvest_actions": 0,
    "deposit_actions": 0,
    "sale_actions": 0,
    "protected_obligation_misses": 0,
    "protected_stock_shortfall_units": 0,
    "carry_units": 0,
    "shed_units": 2
  },
  "events": [
    {
      "tick": 1,
      "deltas": {"fertilizer_actions": 1, "worker_ticks_used": 1},
      "cash_delta": 0,
      "gauges": {}
    },
    {
      "tick": 5,
      "deltas": {
        "harvested_units": 2,
        "harvest_actions": 1,
        "worker_ticks_used": 2,
        "travel_steps": 1
      },
      "cash_delta": 0,
      "gauges": {"carry_units": 2}
    }
  ]
}
```

Every event has exactly four fields:

- `tick`: the engine tick at which the observation became true;
- `deltas`: nonnegative increments to the cumulative counters accepted by the trace schema;
- `cash_delta`: the signed cash change observed at that tick; and
- `gauges`: optional absolute `carry_units` and `shed_units` values.

Events must be ordered by nondecreasing tick. Multiple events at one tick are coalesced into one snapshot. An event at the initial snapshot’s tick is rejected as ambiguous: fold that state into `initial_snapshot` instead. An event after the horizon is rejected rather than silently truncated.

## Compile a stream

```bash
python event_trace_builder.py fertilized.events.json \
  --output fertilized.build-receipt.json \
  --trace-output fertilized.trace.json \
  --pretty
```

The receipt uses schema `titan.w10.realized-fertilizer-event-build/v1` and binds:

- the normalized event stream SHA-256;
- the normalized trace SHA-256;
- event and snapshot counts;
- the complete validated trace; and
- a self-verifiable receipt SHA-256.

The plain trace output can be paired with a control trace and passed directly to `realized_fertilizer.py`, then included in `matrix_runner.py`.

## Fail-closed guarantees

The builder rejects unknown or missing keys, malformed SHA values, booleans in integer fields, negative counter deltas, unknown counters or gauges, no-op events, initial-tick ambiguity, decreasing event ticks, events beyond the horizon, oversized inputs, capacity overflow, worker-budget overflow, and action counters not covered by worker ticks. Final trace validity is not reimplemented: the builder calls the canonical W10 trace validator, so its output cannot bypass the certificate contract.

`test_event_trace_builder.py` contains 15 tests covering a complete lifecycle, same-tick coalescing, horizon carry-forward, ordering and horizon failures, malformed deltas, no-op and unknown fields, shared capacity/action-accounting rejection, deterministic hashing, and both CLI output paths.

## Integration sequence

1. Use `producer_surface_scan.py` to locate the current owner’s narrowest observable engine/evaluator seam.
2. Emit one event stream for the control policy and one for the fertilizer treatment from identical comparison identity and starting state.
3. Compile each stream into a strict trace and retain both build receipts.
4. Certify the pair with `realized_fertilizer.py`.
5. Admit the policy only through the explicit required matrix in `matrix_runner.py`.

The event compiler is instrumentation infrastructure. A `CERTIFIED` pair or `ADMIT` matrix still requires real source hashes and real engine observations; illustrative or fabricated events are not game evidence.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
