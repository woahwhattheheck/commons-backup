# TITAN P11 service-calendar resurrection

This packet restores the missing P11 dependency as a **standalone, default-off
certificate**. It does not edit or import the canonical TITAN runtime, route
producers, configs, archives, exports, or defaults.

## What it answers

`service_calendar.admit_bundle(...)` evaluates a finite bundle of explicit
obligations and returns:

- `ready`: obligations executable from the current observed snapshot;
- `overdue`: obligations whose deadline is already behind the current turn;
- `structural_conflicts`: typed, stable reasons the bundle cannot be admitted;
- a deterministic schedule with action and settlement slots when admitted;
- `source_hash` and `certificate_hash` bindings for reproducible readback.

The scheduler accounts for dependency order, engine phase order, per-turn actor
and machine capacity, existing route reservations, cash, inventory, room
capacity, deadlines, and terminal settlement lag. Production cannot fund
consumption in the same phase. Same-phase room release cannot justify a
same-phase drop. Search is bounded and fails closed.

## Run

```bash
cd revenue/kaggriculture/cloud-execution-lab/p11-service-calendar-resurrection-20260909
python -m unittest -v test_service_calendar
python run_service_calendar_certificate.py sample-feasible.json
```

The CLI exits `0` for an admitted bundle, `2` for a valid but rejected bundle,
and `1` for malformed input or I/O failure.

## Integration boundary

A future canonical integration should translate only observed public state and
an already-generated candidate route into this schema, verify the returned
`source_hash`, and consume the certificate at the route-composition seam.
Admission is feasibility evidence, **not** a score or strength claim. A default
enable still requires exact hosted matched games, both seats, declared seeds,
and immutable result receipts.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
