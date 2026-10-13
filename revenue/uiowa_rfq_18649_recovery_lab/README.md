# UIOWA-063 companion: stateful recovery rehearsal lab

**Synthetic preparation asset. Not University evidence or a production recovery procedure.**

Owner: ZZ-TERN-63F / GPT-6 Astra Pro. Operation: `uiowa-063-tern63f-20260919`.
This isolated companion supplies runnable counterexamples and a facilitator packet to
UIOWA-063. It does not replace the recovery assessor or modify its data contract.
No server, external service, database, deployment tool, credential, or network is used.

## Run the whole exercise

Python 3.10 or newer, standard library only. From this directory:

```sh
python lab.py examples.json --format markdown
python lab.py examples.json --format json
python -m unittest -v test_lab.py
python -O -m unittest -v test_lab.py
```

The CLI reads the named fictional JSON packet and writes the complete report to stdout.
It does not write input files or issue deployment operations. Shell redirection is
optional; use a new output path so an existing artifact is not overwritten.
Exit 0 means the scenario packet ran, **not** that all intermediate recoveries succeeded.
Exit 2 means invalid input; stderr describes the issue and stdout contains no partial report.

Start with [TABLETOP.md](TABLETOP.md), then inspect the generated checkpoint report.
`test_lab.py` fixes expected behavior independently of the rendered prose. The six
fixtures intentionally contain failing intermediate states and successful final states.

## What is being modeled

A fictional resource pool has an integer capacity and an initial allocation. An accepted
transaction is a positive allocation or a negative release. Acceptance updates an
external expected ledger; delivery updates the stored projection. Their separation
makes missing work observable even when a service is readable.

Three independent runtime settings control the reader, event producer (`writer`), and
consumer (`worker`). `v1` uses a field named `units`; `v2` uses `quantity`; `bridge`
reads either, rejects contradictory dual fields, and updates the fields required by
its storage layout. A bridge producer deliberately emits v1-compatible events.
A legacy worker updates only its legacy field: expanding a schema does not magically
make old code maintain a new field.

| Action | Required data besides `op` and `at` | Modeled effect |
|---|---|---|
| `runtime` | At least one of reader, writer, worker | Change only the selected runtime settings |
| `submit` | event_id, resource, nonzero integer delta | Accept a unique business event in the external log |
| `deliver` | event_id | Apply one accepted event; optional idempotent defaults to true |
| `replay` | None | Deliver accepted events in acceptance order, skipping applied IDs by default |
| `snapshot` | Unique name | Copy projection rows, application counts and storage layout |
| `restore` | Existing name | Restore those three objects, not runtime, external log or incident clock |
| `expand` | None | v1 storage becomes dual representation |
| `contract` | None | Dual storage drops the legacy field; deliberately not a safety verdict |
| `incident` | note | Start one fictional elapsed-time clock per scenario |
| `verify` | Unique label | Capture all six business and representation invariants |

Actions at the same minute execute in listed order. These are synthetic logical minutes,
not execution wall time. Scenarios start in v1 with no events; the final action must be
`verify`. Unknown operations, misspelled fields, duplicate IDs, backward clocks, unsupported
runtime versions, non-finite values, bool-as-integer, and impossible migration phases
are rejected. Data bounds: 2 MB input, 100 scenarios, 100 resources and 1,000 actions per
scenario, integer magnitudes at most 1,000,000, and labels of 1–500 characters.

## Six invariants, not one green indicator

Every checkpoint preserves readable values, raw rows, expected allocations, event IDs,
application counts, runtime versions, storage layout, and failed checks:

1. Every resource is readable by the configured reader.
2. Stored allocations equal the expected accepted ledger.
3. Every accepted event has an application record, including offsetting transactions.
4. No accepted event was applied more than once.
5. Coexisting legacy and new fields agree.
6. Readable allocations remain within capacity.

`all_model_invariants_hold` is their conjunction. A valid result may be false.
`verified_recovery_minutes` is the interval **from the scenario's incident to that
particular successful checkpoint**, not the first successful checkpoint, a target,
a service-level objective, or a DORA metric. It is null before an incident or while any
invariant fails. A subsequent successful checkpoint can therefore show a larger interval.
The report does not infer service stability between checkpoints.

| Scenario | False reassurance demonstrated | Required model evidence |
|---|---|---|
| R63-CONFIG | Reverting a reader is confused with migrating data | Original storage plus compatible reader |
| R63-SNAPSHOT | Restored service reads successfully but acknowledged writes vanished | Complete external accepted log and replay |
| R63-FORWARD | Old binary cannot consume new-format queued events or contracted rows | Compatible reader and worker before replay |
| R63-REPLAY | Retry duplicates a business effect | Restored application ledger plus idempotent replay |
| R63-MIXED | New and old clients see different allocations | Reconstructed consistent dual state before contraction |
| R63-NETZERO | Correct aggregate total hides two unapplied offsetting transactions | Per-event application accounting |

## Assumptions and limits

The external accepted log is assumed complete, durable, ordered, retained, and outside
the snapshot being restored. Its content and starting balances are trusted model inputs.
If that log is missing in reality, this lab does **not** establish recoverability.
Snapshot state and application counts are copied together, and modeled worker updates
are atomic. No crash between a write and its deduplication record is simulated.

There is no real concurrency, distributed transaction, replication lag, side effect
such as an email/payment, partial backup, malicious input investigation, or unreliable
storage medium. Different listed delivery orders are tested; this is not a proof about
all concurrent executions. Acceptance validates intended capacity, while delivery may
intentionally violate capacity to illustrate a bad replay.

Restoring a projection and replaying events is a teaching mechanism under these
assumptions, not a recommendation to restore any real service. `contract` can discard
a divergent legacy field: the next verification exposes inconsistency against the
external ledger rather than claiming that destructive contraction is safe.

The canonical input SHA-256 identifies the normalized scenario, not raw-file identity,
a signature, authentic evidence, independent provenance, or permission. Reports carry
`synthetic: true`. A passing fictional trace can support an interview question, never
a University maturity score, recovery demonstration, or report finding about actual practice.

## Integration with the assessment work

Keep this packet under its own namespace. A consuming assessor may link a checkpoint
using `(input_sha256, scenario id, checkpoint label)` and preserve its synthetic label,
all invariant results and null timing. Do not turn an intermediate failure into a
University gap; do not turn a final model success into evidence of a staff exercise.
Actual assessment needs independently supplied procedure, execution, timeline and
business-verification records, as described in the worksheet.

## Design reference and attribution

Google's [SRE Workbook, Canarying Releases](https://sre.google/workbook/canarying-releases/)
discusses separately manageable configuration changes, user-meaningful evaluation,
and shared dependencies, including asynchronous work. Those distinctions informed
this exercise's separate runtime controls and verification prompts. The toy ledger,
scenario design, rules and expected results are original TJLabs preparation material;
they are not a Google implementation, endorsement, certification or normative standard.
