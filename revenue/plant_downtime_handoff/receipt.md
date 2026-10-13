# Plant downtime handoff — synthetic run receipt

Status: `WORKING_SYNTHETIC_DEMO`

Fixture `FAULT-SYN-7701` (PLANT-RIVERBEND-DEMO / ASSET-KILN-04-DEMO, overtemp) proves the public engine:

- ordinary processing creates one technician handoff on `TECH_KILN_THERMAL`, one `PARTS_THERMAL_KIT` intent, and one timestamped status receipt;
- an operational hold (`severity=UNKNOWN`) routes once to `HELD_INCOMPLETE` with zero dispatches;
- a duplicate sensor ping (`SENSOR-SYN-1001`) plus a duplicate report (`RPT-SYN-2001`) share the fault-identity idempotency key and keep one dispatch;
- crash after classify, after tech, or after parts leaves a timestamped progress receipt;
- a worker restart that reloads the serialized store resumes to exactly one dispatch;
- rollback of a crashed run returns a clean un-dispatched state; a finished run stays single-dispatched;
- same id with different bytes returns `FAULT_CONFLICT`;
- PII-shaped keys (`operatorName`, phone) are refused and create zero dispatches.

Test command: `node test_plant_downtime_handoff.js`

Expected result: `plant-downtime-handoff: 10 scenarios PASS`.

Limits: synthetic / no live plant / no PII / browser-local proof only. Not a CMMS write, not a purchase order, not a safety decision, not outreach, not a Stripe charge. Entry is $199 for one business day; $2,500 pilot only after fit. cash_usd = 0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
