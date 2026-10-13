# Service-identity ownership and lifecycle assessment

UIOWA-054 · ZZ-QUARTZ-7N4 · operation `uiowa-054-quartz7n4-20260919`.
Internal engineering carrier: Commons issue #16108. This is an offline practice-review instrument, not a storefront, an access-management service, an audit certification or an actual University assessment.

## What is delivered

`assessment.py` validates a metadata inventory, traces declared service dependencies, assesses eight evidence dimensions, and renders deterministic JSON or Markdown. `example.py` emits six wholly fictional ESS/RIS/IAM situations. `test_assessment.py` exercises both intended behavior and malformed-input/output-custody cases. `WORKSHEET.md` is a facilitator-ready interview and evidence instrument; `RECEIPT.json` records the executed validation and exact source hashes.

No external libraries or network services are required. The code does not log in, request credential values, inspect live systems, change privileges, rotate secrets, disable identities, retire services, schedule anything, rate employees or recommend vendors. Input validation is a metadata-contract check, not a new Commons authentication/authorization mechanism.

## Run a complete fictional rehearsal

Python 3.10 or later; commands below run from this directory. Use a new temporary working directory for generated reports. Existing report files are never overwritten by the CLI.

```sh
python example.py > /tmp/uiowa054-inventory.json
python assessment.py /tmp/uiowa054-inventory.json --format json
python assessment.py /tmp/uiowa054-inventory.json --format markdown --output /tmp/uiowa054-review.md
python -m unittest -v test_assessment.py
python -O -m unittest -v test_assessment.py
```

Repository-root test discovery also works:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_service_identity -p 'test_*.py'
```

The CLI returns 0 when valid input was assessed and 2 for malformed input or an I/O failure. A 0 is **not** a readiness or compliance pass: valid input may produce contradictions and follow-up work. Reports are created only after validation; explicit output paths use exclusive creation. Input paths are read only. Do not use shell redirection to an existing report you need to preserve.

## Fictional rehearsal expectations

| Identity | Expected interpretation |
|---|---|
| `svc-shared` | Six applicable dimensions supported by records, transition/retirement not applicable. Its IAM and ESS direct consumers reach four declared services across ESS, RIS and IAM. This is potential dependency impact, not proof of exposure. |
| `svc-transition` | Receiving-owner transition is documented, not demonstrated acceptance. Continuity demonstration predates the effective owner change and is stale for the new arrangement. |
| `svc-departed` | Current owner is recorded as departed; review is overdue. Route follow-up to the service portfolio owner, not to the departed person. |
| `svc-retired-conflict` | A retirement ticket coexists with a declared active consumer. Preserve the contradiction rather than trusting the ticket alone. |
| `svc-unknown` | Absent purpose, privilege rationale, ownership, lifecycle dates and consumer coverage remain unknown. Identity names cannot fill those gaps. |
| `svc-retiring-empty` | An empty list with incomplete consumer coverage cannot establish retirement readiness. |

All organizational roles, services, references and events in `example.py` are invented. The group labels organize a practice exercise; they assert nothing about current University organization, implementation, adoption or maturity.

## Exact input contract

Every object requires exactly the listed fields. Missing knowledge uses `null` where allowed; a missing field or an extra field is a malformed contract. This deliberately excludes password, private-key, secret-value and token-value fields. **It is not a secret scanner:** arbitrary text can still contain sensitive data; curate and sanitize metadata before use.

Identifiers are 1–80 ASCII letters, digits, periods, underscores or hyphens and begin with a letter or digit. Free-text metadata is nonempty, at most 500 characters and contains no ASCII control characters. Dates are real calendar dates in `YYYY-MM-DD`. Arrays permit at most 5,000 rows each; CLI files permit at most 2,000,000 bytes. All foreign keys resolve to records in this same supplied inventory. Duplicate IDs, references and JSON object keys are errors. Non-finite JSON numbers are errors.

### Root

`schema` = `service-identity-inventory/v1`; `as_of` = assessment cutoff date; `evidence_max_age_days` = integer 1–3650, not a boolean; `owners`, `services`, `identities`, `evidence` = arrays. The freshness interval is a proposed assessment parameter, not an institutional requirement or a standards mandate. Discuss and record it before use.

### Owners

`id`, `role`, `status`, `departure_on`. Status is `active` or `departed`. An active role record has null departure; a departed record has a departure date no later than `as_of`. Use organizational role identifiers, not personal contact details. These records describe supplied metadata, not verified employment status.

### Services

`id`, `group`, `criticality`, `depends_on`. Group is ESS, RIS or IAM; criticality is low, medium or high; dependencies are service IDs. Criticality is recorded context, not an automatic risk score. Direct self-dependency is malformed; cycles between different services are accepted and traversed once. The graph may be incomplete even when all references resolve.

### Identities

`id`, `status`, `purpose`, `privilege_rationale`, `owner_id`, `continuity_owner_id`, `consumer_ids`, `consumer_inventory_complete`, `review_due_on`, `expires_on`, `owner_transition`.

Status is active, retiring or retired. Purpose/rationale, owner IDs, lifecycle dates and transition may be null. Consumer IDs are the services *declared to still consume* this identity; they are not observations collected by this tool. Coverage is true, false or null. Transition is null or an object containing `from_owner_id`, `to_owner_id`, `effective_on`. The owners must differ and exist; the change is effective no later than `as_of`. A destination/current-owner mismatch is retained as a report contradiction, not rejected or silently corrected. Planned future changes belong in the interview follow-up log, not the observed-transition field.

A null expiry means “no expiry metadata supplied”, not “never expires”. A due date is overdue only before `as_of`; dates are treated as inclusive civil days. Expiry on the cutoff date is not yet considered elapsed. Returned `expiry_days_remaining` supports discussion of approaching dates without imposing a blanket renewal interval.

### Evidence

`id`, `identity_id`, `aspect`, `kind`, `result`, `observed_on`, `owner_id`, `reference`.

Aspect is ownership, purpose, privilege, renewal, continuity, transition, dependency or retirement. Kind is record, demonstration, interview or procedure. Result is supports, contradicts or unknown. Observation date cannot be after `as_of`. Owner may be null, but supporting ownership/transition/continuity evidence must bind to the relevant role to qualify. Reference is a sanitized evidence locator, not source contents or a credential.

Evidence is scoped to one identity/aspect; there is no cross-identity proof reuse. The record producer is responsible for reading the referenced source and accurately classifying it. The tool does not fetch or authenticate the reference.

## Interpretation rules

- **Observed:** applicable supplied record or demonstration supports the aspect; continuity specifically requires a demonstration. This label describes evidence supplied, not independent verification by the tool.
- **Reported / documented:** an interview or a written procedure supports the assertion without the applicable direct evidence. A continuity record without a demonstration remains reported.
- **Unknown / stale:** missing, non-supporting, wrong-role or out-of-window evidence cannot become a positive finding. Ownership, transition and continuity evidence must also be dated on/after the effective owner change.
- **Contradictory / follow-up:** explicit conflicts persist; departed roles, overdue reviews and unresolved active consumers produce human work. Contradictory records do not silently expire. The curator must reconcile the underlying sources and keep an audit trail before issuing a revised input.
- **Not applicable:** no transition or retirement is declared in this snapshot. This does not establish complete history, indefinite retention authority or absence of older unresolved contradictory evidence.

An empty consumer list becomes usable retirement evidence only with declared complete inventory coverage *and* an applicable direct dependency record. Retirement still needs its own evidence. Even a supported retired record authorizes no mutation.

The reverse graph answers “which declared services might be affected if this identity's direct consumers are disrupted?” It is not a live blast-radius measurement. It neither equates component presence with vulnerability nor implies any compromise.

## Output and integration

`service-identity-assessment/v1` includes the normalized input SHA-256; an explicit cutoff; counts with their denominator (eight dimensions per identity); per-dimension state, reason, all supplied and applicable evidence IDs; direct and transitively affected declared services; and role/effort/dependency follow-up actions. No composite maturity score or employee ranking is produced. Metadata ordering does not change the report or normalized digest; source inputs are never mutated.

`access_changes_authorized` is always false and `compliance_verdict` is always null. “High” priority means an explicit supplied conflict or follow-up condition, not a calibrated security severity. Effort bands are placeholders: small means one-role review, medium means coordinated evidence collection or a rehearsal. Actual estimates require practitioner input.

Consumers should import report data, preserve states and evidence IDs, and label the synthetic provenance. Do not let an integrating report compiler collapse unknown, documented or stale to observed, hide contradictory evidence, or turn exit status 0 into clearance. The kit does not modify adjacent workbench, compiler, component, data-lifecycle or secrets-handling instruments.
