# UIOWA-047 — Test-data readiness and maintenance

An offline assessment instrument for asking whether representative test fixtures are specified, reproducibly refreshed, aligned with changing interfaces, exercised, maintained and cleaned up. It evaluates supplied **metadata and evidence references**, not application behavior. No network calls, credential requests, institutional data collection, production changes or scheduling occur.

**All supplied ESS, RIS and IAM examples and business rules are fictional.** The labels organize a rehearsal; they do not describe University of Iowa systems, policy, staffing or performance. This is not a compliance audit, release approval, peer ranking or institutional finding.

Builder: ZZ-TESSELLATE-41 / GPT-6 Astra Pro. Operation: `uiowa-047-tessellate41-20260919`. Internal work record: [#16109](https://github.com/woahwhattheheck/commons/issues/16109). This repository is an internal source/evidence carrier, not a customer destination.

## Run the complete rehearsal

Python 3.10+ syntax; standard library only. Run from this directory:

```sh
python example.py > example_catalog.json
python assess.py example_catalog.json --as-of 2026-09-19T12:00:00Z --output example_report.json
python assess.py example_catalog.json --as-of 2026-09-19T12:00:00Z --format markdown --output example_report.md
python -m unittest discover -s . -p 'test_*.py' -v
```

From the repository root, the isolated tests run as:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_test_data -p 'test_*.py' -v
```

Exit code **0 means a report was produced**, even when it contains gaps or failures. Exit code **2 means malformed input or an I/O error**. The output path must differ from the input path. Evidence references are opaque labels: the tool never opens or authenticates them. No environment variable or external package is needed. Test imports are isolated by absolute path to avoid collision with other assessment modules.

The included [example report](example_report.md) is generated from `example.catalog()` at the explicit cutoff above. Expected descriptors: four fixtures; eight required boundary cases; three cases with current supporting evidence; one case with a recorded failure; one case with no specification. These descriptors overlap where appropriate and are **not a score**. A case can have a passing fixture and a different failing fixture at the same time.

[WORKSHEET.md](WORKSHEET.md) supplies the editable grouped-interview instrument, lifecycle diagram, fictional fixture specifications, maintenance dependencies and facilitator exercises. [VALIDATION.md](VALIDATION.md) binds the measured tests and generated output to exact source hashes.

## Input data contract, version 1

All listed keys are required; unknown keys are rejected so a typo does not silently remove evidence. Use JSON `null` where permitted, not an empty string or an invented value. Arrays may be empty except the contract list and each contract's required-case list. An empty fixture list preserves the required-case denominator.

| Object | Required fields and meaning |
|---|---|
| Root | `schema_version`: integer 1; `context`: `synthetic-demo` or `assessment-metadata`; `contracts`: array; `fixtures`: array. |
| Contract | `id`: unique nonempty string; `group`: organizational/service label; `version`: current declared interface version; `required_cases`: unique nonempty strings identifying behaviors selected for this assessment. |
| Fixture | `id`: unique; `contract_id`: existing contract; `contract_version` and `fixture_version`: nonempty string or null; `origin`: synthetic, production-derived or unknown; `state`: active or retired. |
| Fixture maintenance | `owner`: accountable team role or null; `maintenance_hours`: nonnegative finite cycle estimate or null; `refresh_interval_days`: positive integer or null; `recipe_ref`: repeatable construction/refresh instructions reference or null. |
| Fixture timing | `created_at`: timezone-qualified timestamp; `cleanup_due_at`: such a timestamp or null; `refreshes`, `cleanups`, `cases`: arrays. |
| Refresh event | `at`, `outcome` (succeeded or failed), `evidence_ref` (nonempty string or null), `fixture_version`, `contract_version`. |
| Cleanup event | `at`, `outcome` (succeeded or failed), `evidence_ref` (nonempty string or null). It describes complete cleanup of this fixture generation, not deletion of an unrelated temporary copy. |
| Boundary case | `id`: a required case for the fixture's contract; `input_class`: metadata-only representative input description; `expected_behavior`: a concrete expected outcome; `runs`: array. |
| Run event | Same fields as a refresh event. The outcome is the result reported in supplied test records, not a result executed by this utility. |

`example.minimal_catalog()` is a one-fixture editable template. `example.catalog()` is the larger worked packet. The strict validator in `assess.validate()` is the executable contract; JSON objects with duplicate keys are rejected by the CLI. Non-finite numbers, booleans masquerading as numbers, invalid references, duplicate IDs, impossible dates, timezone-free timestamps and ambiguous event ordering are rejected.

For `synthetic-demo`, every fixture must have `origin: synthetic`. The separate `assessment-metadata` mode allows origin metadata to be unknown or production-derived and emits an explicit data-handling follow-up. It is **not** a request to place production records, personal data or secrets into the catalog. Data minimization and permitted use belong in the separately owned UIOWA-059 assessment, not a fabricated conclusion here.

## Evidence semantics

The catalog is a **snapshot supplied for the assessment**. Its interface version, state, owner and due dates must describe the intended assessment snapshot. `--as-of` filters event records; it does not reconstruct historical contract/state/owner transitions that were never supplied. For a historical review, supply the historical snapshot as well as historical records.

Timestamps normalize to UTC. Events at the cutoff are included; later events are excluded and counted per fixture. Each refresh series, cleanup series and case-run series must have unique instants, including timestamps written with equivalent timezone offsets. Runs must occur **strictly after** the applicable refresh; equal timestamps do not establish execution order.

Current supporting case evidence requires an active, already-created fixture with a declared fixture version and matching current interface; the latest eligible refresh must have succeeded with a reference, match both versions and remain within the supplied refresh interval; and the latest case run must have a reference, match both versions and occur after that refresh. A recipe is documented intent, not a demonstrated refresh. A newer failed or unreferenced event supersedes an older success rather than silently resurrecting it. Old-version and expired evidence remains visible in the JSON record context but does not establish current support.

An interval is still current at exactly its boundary and overdue after it. A cleanup is overdue after, not at, its due timestamp. A successful complete cleanup with a reference at or after the latest refresh contradicts an active fixture unless a later refresh demonstrates recreation. **Cleanup of a previous generation does not clear the new generation's cleanup obligation.** Failed or unreferenced cleanup does not count as demonstrated completion.

A missing owner, missing recipe or unknown effort produces a maintenance follow-up; it does not erase otherwise valid case evidence. The `current_evidence_eligible` field is a narrow condition for consuming case-run records, **not overall fixture or release readiness**. Cleanup/retention follow-ups and origin review remain separate from test coverage.

| Output label | Interpretation |
|---|---|
| `supported` | Latest supplied, usable case-run record says succeeded. Not a production guarantee. |
| `failure_recorded` | Latest supplied, usable case-run record says failed. Root cause and production applicability remain to be investigated. |
| `unknown` | Current case support cannot be established from supplied records. Not a zero rating or proof that no testing exists. |
| `UNKNOWN` limitation | Requested evidence or planning information is missing or insufficient. |
| `RECORDED` limitation | Supplied metadata/reference records the condition; the reference is not independently authenticated. |
| `CONTRADICTED` limitation | Supplied records disagree, such as a stale interface version or active inventory after complete cleanup. |

## Report integration contract

`assess(catalog, as_of)` returns a new dictionary without mutating input. `markdown(report)` renders that same dictionary. The top-level keys are `schema_version`, `work_order`, `context`, `as_of`, `catalog_sha256`, `scope_notice`, `summary`, `coverage`, `fixtures`, `limitations`.

`coverage` has one row for every `(contract_id, case_id)` in the selected required-case universe. Preserve `declared_by`, `supported_by`, `failure_recorded_by` and `unknown_by` independently. A required case with an empty `declared_by` is a specification/sampling question, not proof of a universal organizational defect. A passing fixture must not hide another fixture's recorded failure. Do not average across groups or infer peer percentiles.

`limitations` links each reason code to a fixture, optional case, consequence, next action, accountable role, cycle-effort estimate and supplied references. The same `maintenance_hours` estimate repeats on multiple limitation rows for the **same fixture cycle**; deduplicate by fixture before any workload calculation. Missing effort is unknown, not zero. The utility deliberately does not rank tasks using arbitrary weights.

The canonical catalog digest sorts object keys and uses compact UTF-8 JSON without non-finite values. It includes the input array order and all supplied records, even future records excluded from the current assessment. Reordered inputs can have a different digest while yielding identical analytical rows; this records input identity rather than pretending every equivalent representation has identical bytes. The pretty-printed catalog file digest is a different quantity. Preserve the report cutoff and scope notice alongside its digest.

Markdown escapes user-controlled HTML, links, table delimiters and newlines; the JSON preserves their literal values. Treat exported JSON as data, not instructions or executable templates. This utility has no network effects and is not a full untrusted-file sandbox or a substitute for source validation.
