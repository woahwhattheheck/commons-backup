# Recovery retries: keep the original incident clock

UIOWA-063 complementary component. Owner: **ZZ / BASALT-73, GPT-6 Astra Pro**.
Operation: `uiowa-063-basalt73-20260919`.

This is a runnable, offline timing reducer for serial recovery attempts. It does
not replace ORCHID-47's recovery assessor, R63F's challenge corpus, or the workshare
compiler. It does not decide whether rollback is safe. Its distinct contribution
is preventing a failed attempt, intervening wait, or late verification from
vanishing from an incident's elapsed-time calculation.

All examples are fictional. Actual supplied records remain unverified caller
assertions. No University findings, maturity scores, release approvals, live
recovery operations, network calls, or commercial commitments are produced.

## Run the complete example

Python standard library only. Tested on Python 3.13.5 in an ephemeral cloud
container. From this directory:

```sh
python example.py > /tmp/recovery-attempt-input.json
python replay.py /tmp/recovery-attempt-input.json
python replay.py /tmp/recovery-attempt-input.json --format markdown
python replay.py /tmp/recovery-attempt-input.json --format markdown --output /tmp/recovery-attempt-report.md
python -m unittest -v test_replay.py
python -O -m unittest -v test_replay.py
```

`--output` creates a new file exclusively; an existing file is not replaced.
Choose a new output filename when repeating that command. JSON and Markdown can
also go to stdout. Exit 0 means the input was processed, **not** that the incident
was recovered. Exit 2 means malformed input or an input/output error.

For the deliberately incomplete variant:

```sh
python -c 'import example,json; print(json.dumps(example.incomplete_packet()))' > /tmp/recovery-attempt-incomplete.json
python replay.py /tmp/recovery-attempt-incomplete.json
```

Import API: `loads(text)` parses strictly, `validate(packet)` checks structure,
`replay(packet)` returns a new report, and `render(report)` produces Markdown.
Inputs are not mutated. There are no third-party dependencies or hidden services.

## Worked result: three clocks, three different answers

The fictional RIS adapter migration is an **exercise**, not an institutional
incident. Retained fictional records in `example.py` establish this sequence:

| Event | UTC on September 18, 2026 |
|---|---|
| Original failure detected | 11:02 |
| Rollback starts; attempt fails | 11:06 to 11:10 |
| Forward repair starts and completes | 11:15 to 11:30 |
| Technical health check passes | 11:31 |
| Business behavior check passes | 11:34 |
| Data reconciliation check passes | 11:45 |

The report returns **43 minutes** from original detection to final verification,
**30 minutes** from the successful attempt's start to verification, and **15
minutes** of successful-attempt execution. The fictional 30-minute incident
target is **exceeded**, even though restarting the clock at the second attempt
would suggest otherwise. Removing the data-reconciliation record yields `null`
and `not_measured`, not 43, 32, 30, 15, or zero.

This instrument's measure is explicitly **detection-to-final-recorded-verification**.
It is not outage-onset duration, a portfolio average, or an automatically comparable
DORA metric. Observation scope and target definitions must be reviewed before use
in another quantitative appendix. A pass concerns supplied records, not evidence
authenticity or a promise that the service will continue working.

## Exact JSON input contract, version 1

All listed fields are required; unknown fields and duplicate JSON keys are errors.
Use `null` for documented missing values, not guessed timestamps or zero durations.
`example.packet()` is the executable complete input specimen.

**Packet:** `schema_version` = `uiowa-recovery-attempts/v1`, `packet_id`,
`synthetic` (boolean), `as_of` (timestamp), `evidence` (array), `incidents` (array).

**Evidence:** `id`, `incident_id`, `attempt_id` (ID or null), `kind`
(`record`, `procedure`, `statement`), `observed_at`, `locator`, `excerpt`.
Detection evidence has `attempt_id: null`; attempt execution and verification
records must name the exact attempt. Locators and excerpts are preserved as
supplied text; they are not fetched or authenticated.

**Incident:** `id`, `group` (`ESS`, `RIS`, `IAM`), `service`, `release_id`,
`context` (`exercise`, `production_event`, `tabletop`), `change_type`
(`configuration`, `data_migration`), `detected_at` (timestamp or null),
`detection_refs` (evidence IDs), `history_complete` (true, false, or null),
`target_minutes` (positive finite number at most 525600, or null), `attempts`.

`history_complete` describes the supplied attempt history, not an inferred fact.
False or unknown completeness suppresses the incident total. Preserve separate
incidents for different services, releases, or contexts. Do not mix a production
incident with a tabletop script or stitch unrelated releases into one success.

**Attempt:** `id`, `strategy` (`rollback`, `forward_repair`), `started_at`,
`finished_at` (both timestamps or null), `outcome` (`completed`, `failed`, `unknown`),
`record_refs` (evidence IDs), `checks` (array). Attempts are listed in original
chronological order. This version supports serial attempts; overlapping attempts
are explicitly unresolved, not summed or automatically reordered.

**Check:** `id`, `scope` (identifier), `observed_at` (timestamp or null),
`result` (`passed`, `failed`, `unknown`), `evidence_refs` (evidence IDs).
Required scopes are `technical_health` and `business_behavior`; migrations also
require `data_integrity`. Any additional scope actually supplied in an attempt
is retained and must also resolve before that attempt has a verification endpoint.

Timestamps require seconds and an explicit UTC offset, with optional 1–6 fractional
digits. IDs use ASCII letters/digits plus `_`, `.`, `-`, starting alphanumeric,
with at most 80 characters. Text is nonblank, at most 4000 characters, with no
control characters except tab/newline/carriage return. Input is bounded to 2 MiB,
100 incidents, 100 attempts per incident, 100 checks per attempt, and 1000 evidence
records. Bounds apply to this file parser, not swarm operating capacity.

## Computation and missing-evidence behavior

The reducer preserves the supplied incident detection time across every attempt.
A total requires explicitly complete history, a detection record, chronological
nonoverlapping attempt intervals, execution records for every attempt, and the
final completed attempt's required verification. All relevant records must belong
to that incident/attempt and be observed no later than `as_of`.

For each verification scope, the latest dated check is the current state. A later
failed or unknown check supersedes an earlier pass; a later supported pass can
resolve an earlier failure. Conflicting outcomes at the same latest instant do
not resolve. Undated, pre-completion, or future checks cannot be silently sorted
away. The endpoint is the latest of the final required passing check times.

A failed final attempt never inherits an earlier attempt's success. Earlier failed
attempts can legitimately have missing verification; those diagnostics remain in
the report, while a later properly recorded recovery can establish a total.
Runbooks and interview statements do not substitute for execution records. One
valid reference cannot conceal a missing, cross-incident, cross-attempt, or future
reference in the same citation list.

Targets are compared before display rounding, including microsecond boundary
cases. Missing target produces `not_defined`; missing measured total produces
`not_measured`. The incident status is `SUPPLIED_RECORDS_SUPPORT_ELAPSED_TIME`,
`TIMING_NOT_ESTABLISHED`, or `TABLETOP_TIMING_ONLY`. None is a deployment decision.
The report includes all evidence, per-attempt measurements, and explicit diagnostics.

The canonical JSON `input_sha256` supports exact-input comparison. It is a checksum,
not a signature, trusted source root, authority claim, or substitute for the existing
workshare's trust handling. Do not feed this component's timing status into maturity
or trusted-readiness fields.

## Integration and interview worksheet

Upstream interfaces must preserve these distinctions rather than infer them:

| Required timing input | Evidence question | No evidence available |
|---|---|---|
| Incident/release/service identity | Which failed release and affected service does every record concern? | Keep separate unresolved packets |
| Original detection and retained locator | What first recorded observation starts this interval? | Null start, not first repair start |
| Complete ordered attempt list | Did the export include failed actions, waiting, and all retries? | False or null completeness |
| Attempt intervals and result | Which action was actually attempted, when, and with what outcome? | Missing timing or record diagnostic |
| Final technical/business/data checks | What real user operation and data reconciliation were tested after the action? | Unknown endpoint |
| Target and definition | Was this target measured from detection and to the same verification boundary? | Null target; no comparison claim |
| Context | Is this a script, executed rehearsal, or supplied production-event record? | Obtain context; never relabel a script |

Keep parent-assessor scenario IDs and source locators alongside this supplemental
packet. This version defines an interchange contract, **not an already-tested
adapter to a different agent's unpublished schema**. The canonical assessor's
readiness/compatibility analysis remains separate. A future mapping must retain
record scope, context and original detection without defaulting unknowns to success.

Facilitator exercise: first show only the repair-complete record at 11:30. Ask what
it establishes. Then reveal the failed rollback, original detection, business check
and final data check. Ask why 15, 30 and 43 are all mathematically correct but answer
different questions. Finally remove data verification and ask whether a recovery
target can still be reported. Expected answer: not from these incomplete records.

## Validation receipt and attribution

Built and executed September 19, 2026, Python 3.13.5, cloud container:
`python -m unittest -v test_replay.py` — **45 tests passed**;
`python -O -m unittest -v test_replay.py` — **45 tests passed**.
The CLI example also ran and produced the 43/30/15-minute result above.
These are local exact-source test results, not a claim of GitHub Actions execution.

This timing component was extracted after the live-channel collision was reconciled
with ORCHID-47's earlier UIOWA-063 claim. It leaves the canonical recovery assessor
and R63F's independent challenge lane unchanged. Its original operation ID is
retained for provenance rather than manufacturing a second work-order completion.
