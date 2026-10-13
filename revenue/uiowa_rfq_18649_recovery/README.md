# UIOWA-063 — Release recovery evidence kit

**SYNTHETIC PREPARATION. Not University findings, a production runbook, a readiness certification, or authorization to change a system.**

This kit turns supplied recovery records into a repeatable evidence worksheet. It distinguishes a written procedure, a tabletop discussion, an executed rehearsal, and a recorded production observation. It is release-specific; backup retention, recovery-point objectives, and full service restoration belong to the separate backup/service-recovery assessment.

## Contents

- `recovery.py`: standard-library-only validator, consistency assessor, and JSON/Markdown renderer. No network calls or deployment commands.
- `example.json`: two entirely fictional records: a reversible configuration rollback and a data migration that needs forward repair and data reconciliation.
- `test_recovery.py`: executable regression suite, including CLI and optimized-Python checks.
- `ASSESSMENT_PACKET.md`: editable interview worksheet, two tabletop exercises, facilitator answer key, and improvement register.

The implementation is independent of shared workbench/compiler code. An integrator may import `assess(packet)` and `markdown(report)`, or consume the versioned JSON output. Preserve the input packet alongside the output: evidence identifiers and summaries remain in the input ledger, while the report records scenario/attempt identifiers and consistency diagnostics. This kit does not create report findings or update another agent's register automatically.

## Run from the repository root

Python 3.10 or later is required. There are no third-party packages.

```sh
python revenue/uiowa_rfq_18649_recovery/recovery.py revenue/uiowa_rfq_18649_recovery/example.json
python revenue/uiowa_rfq_18649_recovery/recovery.py revenue/uiowa_rfq_18649_recovery/example.json --format json --output /tmp/recovery-report.json
python -m unittest discover -s revenue/uiowa_rfq_18649_recovery -p test_recovery.py -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_recovery -p test_recovery.py -v
```

For Windows, replace `/tmp/recovery-report.json` with a writable output path. The output directory must already exist. The CLI refuses to overwrite its input, including aliases resolving to the same file; other named output files are atomically replaced. Use a new output filename to preserve earlier report versions.

Exit codes: `0` means a valid report was rendered; `1` means `--fail-on-gaps` was requested and at least one scenario lacks supported recovery evidence; `2` means invalid input or an I/O failure. A valid incomplete record still renders without `--fail-on-gaps`. The flag is an evidence-coverage check, **not** a deployment approval or an assertion that recovery targets were met.

## Expected fictional results

| Scenario | Decision | Detection | Execution | Failure to command completion | Failure to verified recovery | Draft target |
| --- | --- | --- | --- | --- | --- | --- |
| CFG-01 / ESS | Rollback; compatibility explicitly recorded | 2 min | 7 min | 12 min | 15 min | 20 min: met in this invented observation |
| MIG-01 / RIS | Forward repair; rollback incompatible | 3 min | 18 min | 30 min | Unknown: data check unavailable | 45 min: unknown |

The fixture yields two scenarios and one `evidence_supported` case. MIG-01 remains `gaps_in_supplied_records` even though its service check passes. In the fictional follow-up exercise, supplying the missing data-verification record and changing its result to `pass` produces a 37-minute verified recovery. Merely deleting the data check cannot make a migration pass.

Targets of 20/45 minutes and the 90-day exercise window are **invented exercise assumptions**, not University objectives, service-level agreements, universal standards, or agreed commitments.

## Input contract: `uiowa-recovery/v1`

All listed keys are required. Unknown object keys are rejected, avoiding silent misspellings. Use `null`, an empty reference list, or an empty attempts list where the contract permits unknown or absent evidence; do not fabricate timestamps or fill unknown durations with zero.

| Object | Fields and meaning |
| --- | --- |
| Packet | `schema` exactly `uiowa-recovery/v1`; `synthetic` boolean; `as_of` timezone-aware timestamp; `max_exercise_age_days` integer 1..36500; `evidence` list; `scenarios` list of 1..1000 records |
| Evidence | `id` unique identifier; `scenario_id` existing scenario; `kind` procedure/decision/execution/verification; `available` boolean; `recorded_at` timestamp; `summary` nonempty text |
| Scenario | `id`; `group` ESS/RIS/IAM; `title`; `change_kind` configuration/application/data_migration; `procedure_refs` evidence IDs; `decision`; `target_minutes` positive finite number or null; `attempts` list |
| Decision | `strategy` rollback/forward_repair/undecided; `rollback_compatible` true/false/null; `owner_role` and `rationale` text or null; `evidence_refs` list |
| Attempt | Globally unique `id`; `mode` executed_rehearsal/production_observation/tabletop; `strategy` rollback/forward_repair; `environment` descriptive text; `times`; `evidence_refs`; `verification` list |
| Times | `failure`, `detected`, `decision`, `start`, `complete`: each timestamp or null |
| Verification | `aspect` service/data; `result` pass/fail/unknown; `at` timestamp or null; `evidence_refs` list |

Identifiers begin with a letter and contain only letters, digits, underscores, dots, or hyphens, up to 80 characters. Ordinary text is limited to 4000 characters per field. Timestamps include seconds and an explicit `Z` or numeric UTC offset. The input file is UTF-8 JSON, limited to 2 MiB; duplicate JSON keys and non-finite JSON constants are rejected. Evidence records are limited to 20,000. References must not be duplicated within a list. An unresolved reference is rendered as an evidence gap rather than quietly discarded.

`recorded_at` means the timestamp of the supporting record as supplied, not the date someone imported it into this kit. An execution record must not predate completion; a verification record must not predate its observation. For log excerpts, use the relevant completed record or excerpt's end, not the creation time of a long-lived log file. `available=true` is the operator's declaration that the record was actually supplied. The tool does not independently open or authenticate that source.

## Interpretation rules

`evidence_supported` means the supplied metadata forms a consistent, sufficiently complete chain under this kit's rules. It is **not proof that a recovery occurred**, that an artifact is authentic, that a test was adequate, or that the current release is safe. A qualified reviewer still inspects original records, checks version/environment representativeness, and makes the assessment judgment.

A scenario requires supported procedure and decision records and a supported latest executed attempt. Selecting rollback requires an explicit `rollback_compatible=true`; `false` and `null` are distinct. The current strategy must match the execution record. A procedure without execution is `documented_only`; a discussion is `discussion_only`. Missing records remain unknown; a gap in this packet is not automatically a gap in the organization's practice.

Every executed attempt needs complete, nondecreasing timestamps and available execution evidence. Required service verification must pass after completion. Data migrations additionally require passing data verification; a recorded data check on any other change is also considered. Latest observations per aspect are used. Simultaneous contradictions, undated observations, future observations, wrong-scope evidence, unavailable evidence, and invalid chronology prevent an affirmative result. Earlier failures remain in the input and may be superseded by a later, supported observation.

The latest executed attempt is selected by failure timestamp. An older successful rehearsal cannot hide a newer unsuccessful or incomplete attempt. Missing ordering timestamps and tied latest attempts produce explicit uncertainty rather than an arbitrary winner. A current strategy change invalidates the earlier strategy's demonstration for this assessment.

Durations are separate measurements: failure-to-detection, detection-to-decision, execution start-to-completion, failure-to-completion, and failure-to-the-last-required-passing-verification. Only the last measures verified recovery in this kit. Partial durations may be reported when their endpoints are known; contradictions suppress them. Target and age comparisons use unrounded values; reported durations are rounded to six decimal places.

A demonstrated recovery can miss its proposed target. The report preserves both facts; it does not convert a slow but documented exercise into missing evidence. `--fail-on-gaps` evaluates support, not target attainment. The age window is caller-supplied and measured from execution completion to the explicit `as_of`; stale evidence is retained with a follow-up diagnostic.

## Safe handling and limitations

Use invented identifiers for demonstrations. Do not paste credentials, live data, personal records, private endpoints, or sensitive operational details into this public repository. The strict field contract is not a secret scanner: a secret placed in an ordinary text field would still be text. Keep real assessment source material in its agreed restricted location and use appropriately redacted identifiers only.

The model does not assess recovery-point objectives, data-loss tolerance, service dependencies, repeated-failure statistics, automatic remediation, production approval, or source authenticity. A single observation does not establish future reliability. The two examples do not represent the whole three-group assessment; an IAM case can be added using the same contract without inventing University facts.

Operation: `uiowa-063-quartz17-20260919`. Builder: ZZ-QUARTZ-17 / GPT-6 Astra Pro. Work record: #16105.
