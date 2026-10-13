# UIOWA-070 — seasonal capacity and dependency planning

A working, offline planning aid for interviews and recommendation preparation. It reads explicitly supplied demand/capacity assumptions, propagates offered requests through shared dependencies, splits a calendar at every event/maintenance boundary, and compares preparation alternatives. It does not measure or load-test any system, schedule events, change fleet behavior, select vendors, or assign maturity scores.

**The checked-in example is entirely SYNTHETIC.** The April 15, 2030 dates, roles, systems, rates and effort estimates are fictional. ESS/RIS/IAM identify example assessment groups; none of the example records establishes a University practice, actual calendar, service capacity or staff availability. Real engagement records belong in the approved private evidence location, not this repository.

## Run the published component

Python 3.10+ syntax; executed here on Python 3.13.5. Standard library only, no installation or network required.

```sh
cd revenue/uiowa_rfq_18649_seasonal_capacity
python planner.py synthetic.json --out /tmp/uiowa-070-demo
```

On Windows, use a new chosen output folder instead of `/tmp/uiowa-070-demo`.
The CLI writes five UTF-8 artifacts to the specified folder:

| Artifact | Purpose |
|---|---|
| `report.json` | All scenarios, interval/service observations, root-demand contributions and source references; canonical input digest |
| `report.md` | Readable scenario comparison, dependency calendar, evidence register and preparation requirements |
| `capacity.csv` | Per-service ranges, ownership, pressure/unknown states and root contributions |
| `calendar.csv` | Half-open UTC windows, concurrent events, maintenance and affected dependencies |
| `options.csv` | Unchanged baseline and independently evaluated alternatives, effort ranges and validation needs |

Existing files with these five names in the chosen folder are replaced. Other files are not touched. Use a new folder for each saved scenario; no scheduler or cleanup process is installed. Input is fully parsed and analyzed before output creation. Malformed input returns exit 2 with a diagnostic; valid input returns exit 0 and a JSON receipt. Partial filesystem failure can leave a partly written output folder; do not treat that as a complete delivery.

## Rehearsal: a shared dependency changes the answer

Run the command above and inspect the baseline window `2030-04-15T10:00:00Z` to `10:30:00Z`. All numbers below are calculated from invented inputs, not observed measurements.

| Service | Offered requests/s, low / typical / high | Usable capacity requests/s | Result |
|---|---|---|---|
| ESS | 75 / 108 / 142 | 144 / 176 / 208 | Within assumed envelope |
| RIS | 22 / 39 / 56 | 64 / 80 / 96 | Within assumed envelope |
| IAM | 50 / 85 / 120 | 128 / 160 / 192 | Within assumed envelope |
| AUTH shared identity | 112.5 / 210 / 325 | 40 / 48 / 56 | Pressure under all supplied assumptions |
| DB shared database | 221 / 343 / 467 | 128 / 160 / 192 | Pressure under all supplied assumptions |
| EXT external dependency | 27.625 / 60 / 121 | Unknown | Unknown capacity, not zero |

Typical AUTH offered load is `5 + 108*0.75 + 39 + 85 = 210`; usable capacity during maintenance is `120*(1-0.2)*0.5 = 48`. Typical DB offered load is `10 + 108*2 + 39*3 = 343`; usable capacity is `200*(1-0.2) = 160`. The trace preserves the registration, research and sign-in contributions separately. A worksheet that examines only application capacity misses both shared constraints.

At 12:30, the unconfirmed fictional cutoff has unknown RIS demand. RIS, AUTH, DB and EXT therefore retain unknown demand; ESS and IAM remain separately interpretable. At exactly 13:00 that increment is no longer active. The model never fills the missing estimate with zero.

| Scenario | Pressure clock-hours | Pressure service-hours | Unknown service-hours | Typical excess service-request equivalents |
|---|---:|---:|---:|---:|
| Baseline | 3.5 | 6.5 | 7.5 | 1,688,400 |
| Move AUTH maintenance | 4.5 | 7.5 | 7.5 | 1,515,600 |
| Reduce repeated reference-data reads | 3.5 | 6.5 | 7.5 | 1,018,800 |
| Both changes | 4.5 | 7.5 | 7.5 | 846,000 |

This preserves an unfavorable tradeoff: moving maintenance reduces typical excess load but exposes another interval to possible pressure at the low capacity/high demand bounds. Read consolidation lowers load without resolving the identity or unknown external constraint. Do not reduce these different measures to a single success score. Effort ranges are 2–6, 8–24 and 10–30 assumed person-hours respectively; they are not elapsed delivery promises or available staffing.

Pressure clock-hours count each interval once when any resource has modeled pressure. Pressure service-hours sum those intervals across resources. Unknown service-hours count a resource interval once when demand or usable capacity is unknown. These are not predicted downtime.

Excess service-request equivalents integrate the positive offered-minus-usable range over time, excluding unknown rows. They count service calls across resources, not unique users, lost requests, queued work or measured errors. A reduction is a change in the supplied model, not demonstrated production benefit. Use the unknown-hours measure beside it.

## Exact input contract

`synthetic.json` is an editable example; `planner.py` validates both structure and semantics. Every object has exactly the fields listed here. Unknown numeric ranges use JSON `null`; omitted fields, empty strings and the text `"unknown"` are not equivalent substitutes.

| Object / collection | Required fields |
|---|---|
| Root | `schema_version`, `classification`, `title`, `period`, `sources`, `services`, `edges`, `events`, `maintenance`, `options` |
| `period` | `start`, `end` |
| `sources[]` | `id`, `kind`, `locator`, `note` |
| `services[]` | `id`, `group`, `owner_role`, `basis`, `baseline_rps`, `capacity_rps`, `reserve_fraction`, `source_refs` |
| `edges[]` | `id`, `from`, `to`, `calls_per_request`, `basis`, `source_refs` |
| `events[]` | `id`, `title`, `start`, `end`, `owner_role`, `basis`, `source_refs`, `increments` |
| `maintenance[]` | `id`, `service`, `start`, `end`, `capacity_fraction`, `owner_role`, `basis`, `source_refs` |
| `options[]` | `id`, `title`, `owner_role`, `effort_hours`, `prerequisites`, `validation_needed`, `source_refs`, `changes` |
| `changes[]` | `collection`, `id`, `field`, `value` |

Schema version is `uiowa.seasonal-capacity.v1`. Classification is `SYNTHETIC` or `PLANNING_INPUT`; classification is a label, not approval or verified truth. Source kinds: `synthetic`, `observation`, `interview`, `contract`, `assumption`, `unavailable`. Synthetic packets must label every source synthetic. Every evidence reference must resolve to a source ID. For real planning, include source version, observation window, exact section or record locator and applicability in the locator/note; the planner validates references, not source content or truth.

IDs are unique within each collection. At least one service is required. Group is `ESS`, `RIS`, `IAM`, `SHARED` or `EXTERNAL`. Owner fields contain roles, not personal availability or commitments. Rates and effort are `[low, typical, high]`, finite nonnegative ordered numbers, or null. `capacity_fraction` is bounded by 0 and 1; `reserve_fraction` is a known scalar at least 0 and below 1. Range bounds are not probabilities or confidence intervals.

Timestamps require explicit UTC offsets and whole seconds. Every window is `[start,end)`, has positive duration and lies within the planning period. Offset-equivalent instants coalesce. No IANA-zone or ambiguous wall-clock resolution is attempted. `increments` maps existing service IDs to incremental offered request-rate ranges or null. Baseline and active increments are added, not overwritten.

Each edge is effective downstream calls per upstream request, inclusive of any modeled retry behavior. The graph must be acyclic; repeated service pairs are rejected. Represent finite retry amplification inside an effective ratio with an evidence basis, not an infinite recursive graph. Multiple distinct call paths add: a diamond is not deduplicated unless the effective ratios explicitly represent that behavior.

Options are independent modifications of the unchanged input. Supported fields: services `capacity_rps`/`reserve_fraction`; edges `calls_per_request`; events `increments`/`start`/`end`; maintenance `capacity_fraction`/`start`/`end`. They cannot silently change evidence, owners or group identities. Option evidence is appended to affected rows. Duplicate field changes, missing targets and invalid resulting windows are rejected. Effort and prerequisites remain visible rather than becoming an automatic action.

## Method and limits

For each interval and service, `offered = baseline + active increments + incoming offered calls`. Nonnegative range arithmetic propagates low/typical/high bounds separately, retaining original root contributions. Unknown multiplied by a known zero contributes zero; other unknown paths remain unknown. Overload does not silently throttle downstream offered demand: this is not a queueing, caching, burst-arrival or backpressure simulator.

`usable = capacity * (1-reserve) * retained maintenance fraction`. Concurrent maintenance records on the same service produce unknown combined capacity; the planner does not guess independence and multiply them. A written maintenance plan does not establish retained capacity.

Headroom bounds are `[capacity.low-demand.high, capacity.typical-demand.typical, capacity.high-demand.low]`. `PRESSURE_ALL_ASSUMPTIONS` means demand.low exceeds capacity.high; `PRESSURE_SOME_ASSUMPTIONS` means demand.high exceeds capacity.low. Equal boundary, within-envelope, no modeled demand, unknown demand and unknown capacity remain different states. Within-envelope is not evidence of latency, availability, data correctness, staffing readiness or a provider commitment.

Decimal arithmetic is used internally; exported numbers are finite JSON numeric approximations. This is not exact-money accounting. Extremely large derived values that cannot be represented finitely are rejected. CSV uses empty numeric cells for unknown, preserving literal zero. Text beginning with a formula marker is apostrophe-prefixed for spreadsheet consumption; JSON remains the lossless canonical representation. CSV is an export, not a round-trip input adapter.

## Integration and evidence collection

Import `analyze(packet)` for a JSON-serializable report, or use the CLI. `scenarios[].capacity[]` retains service/group, time bounds, source references, contributing roots and interpretation state. `scenarios[].option` retains hypothetical change, effort, prerequisites and evidence still needed. Downstream adapters should namespace IDs with this component and input digest, preserve native status fields as extensions, and never cast pressure or unknown into an assessment rating.

This component produces planning evidence, not an authoritative compiler report. It does not replace `../uiowa_rfq_18649_workbench` or the parent workshare compiler. No compiler or roadmap adapter is claimed here. The existing integration/catalog operators can consume these stable fields without editing this component.

Use `worksheet.md` to collect actual calendars, same-workload demand/capacity evidence, effective call ratios, external dependencies, maintenance feasibility and role-capacity constraints. `synthetic_sources.md` supplies the fictional source material for the worked example. Preserve uncertainty until the relevant evidence is collected.

## Validation and publication state

The implemented planner and fixture were exercised with 29 local regression tests under normal Python and 29 under `python -O`, including hand-calculated shared loads, unknown propagation, zero versus unknown, duplicate/cyclic dependencies, maintenance overlaps, independent alternatives, invalid timestamps, finite numeric output and portable exports. The standalone test-file publication was blocked twice by the connector's safety-status evaluation; that file is not advertised as present. This is a known reproducibility gap for the full regression suite, not a claim that it was merged. The published CLI, complete fixture and hand-worked expectations above remain independently runnable. See the PR for exact source hashes and verification scope.

Operation: `uiowa-070-deltaweir63-20260919`. Builder: ZZ-DELTAWEIR-63, GPT-6 Astra Pro. Internal work record: issue #16124.
