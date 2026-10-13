# Fictional misfueling scenario desk

A dependency-free local CLI for importing fictional plan, order, aircraft, equipment and observation records, explaining inconsistent or missing conditions, and retaining a replayable handoff.

This completes the simulation source requested in [Commons #16018](https://github.com/woahwhattheheck/commons/issues/16018), preserving Z-Sol-3917's original scope and credit. Continuation: `YPF-MISFUEL-SIMULATION-20261003-01`.

**This is simulation software.** It cannot read an operational PAD system, authenticate an observation, operate equipment, enable fueling, or authorize dispatch or a pilot. All identities, products, quantities, age limits and checks are supplied fictional scenario facts. The example values are arbitrary demonstration values, not aviation thresholds or instructions.

## Run the operator workflow

Use Python 3.10 or newer. No installation or third-party package is needed. Work in a separate directory so scenario files stay outside the source checkout:

```sh
python /path/to/barrier.py template --at 2026-10-03T12:00:00Z --out scenario.json
python /path/to/barrier.py check scenario.json --at 2026-10-03T12:00:00Z --out handoff-pending
python /path/to/barrier.py verify handoff-pending
```

`template` writes a complete, editable fictional scenario with both prechecks explicitly false. The first `check` therefore writes a `HOLD` handoff and exits **1**. Its local alert is `PRECHECK_NOT_PASSED`, with a path for each unfinished check. A successful `verify` exits **0** while preserving the saved `HOLD` state.

Open a copy of `scenario.json` in a text editor. Supply the desired fictional records and their evidence references. To demonstrate the consistent case, change the two `prechecks[].passed` declarations to JSON `true` and replace their pending evidence references with the fictional observation labels used in your demonstration. Save the copy as `scenario-complete.json`, then:

```sh
python /path/to/barrier.py check scenario-complete.json --at 2026-10-03T12:00:00Z --out handoff-complete
python /path/to/barrier.py verify handoff-complete
```

Both commands exit **0**, and the simulation state is `READY_FOR_SUPERVISED_PILOT`. Despite that inherited state name, it only means that the supplied fictional conditions satisfy this model. It is not a readiness, certification or authorization statement. `live_control`, `live_dispatch_authorized` and `source_authenticity_verified` remain false in both states.

Use a new file or directory for every output; existing destinations are never overwritten. Omitting `--at` uses current UTC. Supply an explicit reference time when demonstrating or comparing historical scenarios. All timestamps use `YYYY-MM-DDTHH:MM:SSZ`.

## Import contract

The template is the complete schema example. Import JSON as UTF-8 without a byte-order mark. Root `schema` must be `ypf-misfuel-simulation-v1` and `evidence_class` must be `FICTIONAL_SIMULATION`.

| Record | Supplied facts and comparison |
| --- | --- |
| `scenario_id` | Traceability label for this fictional scenario. |
| `policy` | Explicit maximum ages for plans, orders, assets, observations and prechecks; required checklist IDs and kinds. |
| `plan` | Current plan ID/revision, aircraft/flight/stand IDs, product, minimum/maximum uplift, issue/expiry times and evidence reference. |
| `order` | Order ID, referenced plan ID/revision, the same aircraft/flight/stand/product, selected equipment, requested uplift, issue/expiry times and evidence reference. |
| `aircraft` | Matching aircraft ID, supplied permitted product list and maximum uplift, issue/expiry times and evidence reference. |
| `equipment` | Matching selected equipment ID and product, issue/expiry times and evidence reference. |
| `observation` | Observation ID plus the order, plan/revision, aircraft, flight, stand, equipment and product observed in the fictional scenario; timestamp and evidence reference. |
| `prechecks` | One record per required check: ID, kind, explicit boolean, timestamp, evidence reference, and the order/observation IDs to which it belongs. |

The required checklist must contain at least one `operator` and one `equipment` check. Each checklist ID and observed check must be unique. Missing, duplicate, undeclared, inconsistent, stale, future or unpassed checks produce local findings. A passed flag is a supplied assertion, never an independently verified act.

Identity strings are compared exactly and case-sensitively. The importer does not trim, infer, translate, select a newer plan, substitute a product, or fill absent fields. Unknown fields produce `HOLD` findings to make misspellings visible.

Quantities are nonnegative decimal **strings**, with at most nine whole digits and three fractional digits. Comparison uses decimal arithmetic without binary floating-point conversion. Requested uplift must be positive, inside the supplied plan interval, and no greater than the supplied aircraft limit. These are fictional comparison values; the program includes no aircraft database, approved product catalogue, units conversion or engineering limits.

Records must satisfy `issued_at <= evaluated_at < expires_at` and their supplied age window. Exact maximum age is accepted; expiry is exclusive. Orders cannot predate the current plan; observations cannot predate any supplied current plan/order/asset record; prechecks cannot predate the referenced observation. Moving to a new plan revision or observation requires the accompanying references and checks to remain consistent.

Input limits are software bounds: 1 MiB per JSON file, 256-character field names/text, 64 fields per scenario object, up to 100 permitted products/checks, positive integer revisions and age windows up to 2,147,483,647, and at most 512 findings. Exceeding a structural bound, invalid JSON/Unicode, duplicate JSON keys, non-finite numbers or the wrong schema/class returns a controlled error. Ordinary missing or inconsistent scenario facts produce a retained `HOLD` assessment.

## The retained handoff

Each output directory contains exactly four files:

| File | Contents |
| --- | --- |
| `input.json` | Exact imported bytes, including original whitespace and ordering. |
| `assessment.json` | State, supplied context, sorted alert codes/reasons with input paths, assessment time and unchanged false authority fields. |
| `assessment.md` | Readable decision, context and local findings. |
| `manifest.json` | Each member's byte count/SHA-256, the executing `barrier.py` SHA-256, recorded reference time and deterministic receipt digest. |

`verify` reads the retained original input and recorded reference time, recalculates the decision and regenerates every member with the current script. It requires exact byte equality of all four files. Source edits, changed input, edited reports, altered manifest fields and partial directories are rejected. Keep the same published `barrier.py` generation with a handoff; a changed script requires a new assessment generation.

Replay verifies calculation and retained-byte consistency. Hashes are not signatures, source authentication or proof of custody. Someone who changes the facts and regenerates the entire package can create another internally consistent handoff. A saved ready state does not become current by being replayed: evaluate the input again at the current reference time when demonstrating freshness.

Normal reported write failures remove newly created output files. An abrupt process or machine interruption may leave an incomplete directory, which replay rejects; retain or inspect that directory and choose a fresh output location.

## Exit codes and local alerts

| Command/outcome | Exit |
| --- | ---: |
| Template written; consistent fictional assessment; exact replay of either state | 0 |
| Assessment written with `HOLD` findings | 1 |
| Malformed input, file/write error, unsupported schema, or replay mismatch | 2 |

The assessment console prints the fictional evidence class, false live-control/dispatch flags, state, distinct alert codes, finding count, receipt digest and handoff path. Read `assessment.md` or `assessment.json` for the precise input path and reason. A verify success is always reported as `replay: VERIFIED` and includes the original state with the same simulation fields.

## Pilot preparation

[PILOT_PLAN.md](PILOT_PLAN.md) records the current official opportunity, this simulation's evidence ceiling, the reusable demonstration and the organizational/technical evidence still absent. It is internal preparation, not a submission or a live-system design.
