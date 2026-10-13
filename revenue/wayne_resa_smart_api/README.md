# Wayne RESA SMART API response and acceptance lab

**Internal preparation · proposed synthetic contract · no live integration.**

This completes the offline response-lab portion of existing issue **#15914** under
`WRESA-SMART-ERP-API-RESPONSE-ZAXIALFIN2314-20260917`, preserving the original
Z-AxialFin-2314 carrier. ZZ–Keystone-43CF recovered the response materials and
built the outer acceptance journal. The existing `wayne-smart-api-01` reconciliation
shadow remains unchanged in [../wayne-smart-api](../wayne-smart-api/README.md).

The response documents connect the recovered solicitation to a proposed design:
[source register](SOURCE_REGISTER.md), [requirements](REQUIREMENTS.md),
[architecture and delivery](ARCHITECTURE_AND_DELIVERY.md),
[UAT and cutover](UAT_AND_CUTOVER.md), [unaccepted workshare](WORKSHARE.md), and
[submission readiness](SUBMISSION_READINESS.md). The
[October 3 Addendum 2 review](ADDENDUM_2_REVIEW_20261003.md) closes the public A2
source gap and updates the source/readiness crosswalk. Full submission-package,
qualification and actual-interface evidence remain outstanding; submission status
remains **HOLD**.

## What the implementation does

`acceptance_lab.py` runs an explicit, deterministic journal of synthetic operations.
It distinguishes a known failure before sending from an uncertain commit, binds
outcomes to their request and dispatch attempt, and retains individual financial
discrepancies. `rehearsal.py` exercises 18 authored scenarios, including retry
boundaries, stale outcomes, duplicate logical requests, conflicting observations,
and opposing cent discrepancies. Expected outcomes are written independently of
the state reducer; a failed expectation stops output generation.

The original baseline still executes all 150 frozen states: 120 reconciled, 10
duplicate no-ops, 10 unknown-commit holds and 10 unauthorized holds. Its complete
second replay must add no effects, holds, events or protected reads. The new 18
scenarios are a separate proposed acceptance exercise. Neither number establishes
the RFP's coverage targets, actual SMART behavior or client UAT acceptance.

No credentials, endpoint access, network calls, sleeps, AWS resources, payment
activity or authoritative writes are used. This is a sequential simulation;
competing-key examples do not establish concurrent database locking or distributed
exactly-once execution.

## Run the operator rehearsal

Use Python 3.10 or later and the standard library from the repository root.
The recorded execution environment is identified in the published execution receipt.
Choose an output path whose parent exists and whose final directory does not.

```bash
python revenue/wayne_resa_smart_api/rehearsal.py --out /tmp/wayne-smart-rehearsal
python revenue/wayne_resa_smart_api/acceptance_lab.py \
  /tmp/wayne-smart-rehearsal/ordinary-confirmed/transcript.json \
  --verify /tmp/wayne-smart-rehearsal/ordinary-confirmed/report.json
python -m unittest test_wayne_smart_api_response
python -O -m unittest test_wayne_smart_api_response
```

The rehearsal produces 57 files: a JSON and Markdown summary, all 150 expanded
baseline records, and 18 case directories each containing `transcript.json`,
`report.json` and `report.md`. Start with `summary.md`, then inspect the complete
event history in a case report. Every Markdown case retains the exact event claim
objects, including rejected commit IDs, request digests and observation types.

The [executed walkthrough](WORKED_REHEARSAL.md) records the normal/optimized
rehearsal result. [WORKED_REHEARSAL_BUNDLE.json](WORKED_REHEARSAL_BUNDLE.json)
retains all 57 actual UTF-8 output files with paths, byte counts, digests and
contents, including the 150 expanded baseline records. This bundle is evidence;
the commands above regenerate the runnable operator artifacts.

To run an edited synthetic transcript separately:

```bash
python revenue/wayne_resa_smart_api/acceptance_lab.py \
  /tmp/wayne-smart-rehearsal/before-dispatch-retry/transcript.json \
  --out /tmp/wayne-smart-one-case
```

Both commands require a new output directory and create files exclusively.
Existing inputs and output files are never overwritten. The report is prepared
before directory creation; an interrupted or failed write can still leave a
partial **new** directory. Preserve it for inspection and use another new output
path. There is no transactional filesystem claim or automatic cleanup of partial
results. Successful execution returns 0, including an expected simulated HOLD;
invalid input, changed baseline, mismatched replay or output refusal returns 2.

## Proposed transcript contract

The top-level object has exactly `schema`, `synthetic_only`, `profile` and `events`.
Use schema `wayne-smart-offline-transcript/v1` and literal `synthetic_only: true`.
The profile has `profile_id: PROPOSED_OFFLINE_V1`, `max_attempts`,
`backoff_base_ms` and `backoff_cap_ms`. The default 3 attempts, 100 ms base and
1,000 ms cap are design choices, not buyer-specified service settings.

Each event has a unique `event_id`, a nondecreasing integer `at_ms`, a `type` and a
`key` beginning `SYNTH-`. Equal logical times retain input order. Identifiers are
bounded ASCII; transcripts have at most 256 events and 1 MiB of JSON. Duplicate
JSON properties, malformed UTF-8, invalid scalar strings, non-finite numbers,
unknown fields, and invalid event shapes are refused. Cents and times are integers;
booleans and floating-point numbers do not stand in for them.

| Event | Additional required fields | Proposed meaning |
| --- | --- | --- |
| `SUBMIT` | `record_id`, `payload_sha256` | Bind a key to a frozen synthetic logical mutation |
| `DISPATCH` | None | Start one logical attempt; this never sends a request |
| `NOT_SENT` | `dispatch_event_id` | Explicit injected proof that this exact attempt sent nothing; permit a bounded retry |
| `ACK_LOST` | `dispatch_event_id` | This attempt has an uncertain commit; stop dispatching |
| `OBSERVE` | `record_id`, `payload_sha256`, `commit_id`, `observation`, `posted_cents`, `evidence_id` | Inject a transaction-level status observation bound to the submitted identity |

`OBSERVE.observation` is `COMMITTED`, `NOT_COMMITTED` or `UNKNOWN`.
Only `COMMITTED` carries integer `posted_cents`; the other two require JSON null.
Evidence identifiers start with `SYNTH-`. An observation is a fixture claim,
not a live status query or a statement that SMART provides such an endpoint.

Use `load_baseline()` and `request_sha256(record)` when constructing a transcript.
The digest binds mutation key, commit, ledger account and expected cents. It omits
observational record ID/source URI/truth label so original duplicate records
121–130 remain logical duplicates of 1–10. Each operation retains its initially
submitted record and source reference. Reusing a key for a different logical
payload, or a second key for an already bound mutation, creates a visible refusal.
The original unauthorized and unknown-commit fixture states cannot be upgraded
by echoing their fields in an observation.

## State and recovery rules

`SUBMIT` makes an eligible operation `READY`. `DISPATCH` starts `IN_FLIGHT` and
consumes one attempt. Its explicit `NOT_SENT` outcome computes the next due time:
outcome time plus the lesser of the cap and `base × 2^(attempts − 1)`. The outcome
does not consume another attempt. With defaults, refusals at times 0 and 100 lead
to retries at 100 and 300. Earlier dispatch remains `RETRY_NOT_DUE`; exhausted
budget becomes `HOLD_RETRY_EXHAUSTED`.

Every `NOT_SENT` and `ACK_LOST` references its exact dispatch event. A late outcome
for attempt 1 cannot govern attempt 2: it produces `HOLD_STALE_ATTEMPT` without
changing the active attempt, state or retry deadline. An arbitrary timeout or
server error cannot be relabeled `NOT_SENT` by this contract.

`ACK_LOST` and an explicit `UNKNOWN` observation produce `HOLD_UNKNOWN_COMMIT`.
No later `DISPATCH` can resend it. A fully matching, zero-variance `COMMITTED`
observation resolves the operation to `COMMITTED`; `NOT_COMMITTED` instead requires
review and never authorizes an automatic resend. Evidence-ID conflicts and
binding mismatches are retained without adding an accepted commit observation.

The summary deliberately retains **historical** HOLD event IDs after an operation
is resolved. A current state of `COMMITTED` can therefore accompany
`HOLD_REVIEW_REQUIRED`: resolving uncertainty does not erase its history or mark
human review complete. Read `operations[].state`, `summary.unresolved_keys`, and
`summary.hold_event_ids` separately. A scenario matching an expected HOLD passes
that synthetic expectation while continuing to hold the operation.

Financial variance is computed per operation before aggregation. The rehearsal's
100,138 versus 100,137 cents and 100,273 versus 100,274 cents produce +1 and −1.
Their sum is zero, but both operations remain held and the nonzero count is two.
This does not establish actual SMART currency, precision or posting rules.

## Source, replay and limits

The loader captures the unchanged core, fixture and manifest bytes once and checks
their pinned SHA-256 values. It executes those captured bytes against captured
fixture copies in an ephemeral directory. A temporary unique module is removed
after execution; `sys.path` is never modified. The existing files are consumed
unchanged. Their exact Git blobs and SHA-256 digests appear in every report.

Those three source bindings identify the inherited reconciliation baseline.
The separate execution receipt identifies this outer implementation and its test
runtime. A changed baseline refuses execution until its contract and pinned
identity have been reviewed; the lab does not silently accept a new truth set.

The report receipt binds canonical content, and `--verify` reconstructs the entire
report from the saved transcript and pinned baseline before comparing it. Merely
recomputing the outer digest cannot validate an altered result. These are content
digests, not digital signatures, authenticated operator identities, immutable
storage, a production journal or buyer approval.

The documents identify the remaining qualification, source, interface, deployment,
coverage and submission work. No result in this lab authorizes an external
submission, customer contact, deployment, financial action or revenue recognition.
