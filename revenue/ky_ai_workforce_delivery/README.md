# Kentucky AI Workforce delivery evidence engine

This package is a deterministic, network-free operational evidence engine for the
Kentucky AI Workforce Readiness Network opportunity tracked in Commons issue
`#13536` (`R-C08-KY-AI-WORKFORCE-2026`). It turns a delivery plan or later delivery
evidence into a source-bound JSON receipt that can be reviewed without silently
normalizing away missing pathways, modality gaps, enrollment drift, attendance
problems, or negative assessment outcomes.

It is useful before a proposal as an implementation/readiness artifact and, if a
qualified team is formed, during delivery as a compact evidence reducer. It is not a
proposal, a buyer acceptance artifact, a partner commitment, a reference, an award,
or payment evidence.

## Operational contract

The validator requires both Service A and Service B. Service A must carry exactly the
five stated occupational pathways: manufacturing, construction, logistics,
healthcare, and business operations. Curricula retain objectives, instructional
minutes, accessibility provisions, and hands-on exercises. Instructor records bind
named capability scopes to `live_remote` and `in_person` delivery modes. The engine
conservatively requires both modes to be operationally coverable for each required
scope; this is a readiness contract, not a claim that the buyer requires every single
session to run in both modes.

Cohorts bind sessions to qualified instructors, timezone-aware schedules, delivery
mode, duration, and seat capacity. Participant identifiers are opaque rather than
email addresses. Attendance is accepted only for a session in a cohort where that
participant is enrolled. Assessment scope must likewise be backed by enrollment in a
matching Service A pathway or Service B cohort. Scores are bounded but negative
pre/post deltas are preserved. Reporting controls explicitly retain outcome fields,
record-retention controls, and accessibility controls.

The opportunity's approximately 980 participants are treated as a planning target,
not a guaranteed minimum. Falling below the target produces a warning rather than a
fabricated responsiveness failure. The report always carries false authority flags
for buyer acceptance, partner commitment, proposal submission, award, and payment.

## Usage

From the repository root:

```sh
python -m revenue.ky_ai_workforce_delivery.delivery \
  revenue/ky_ai_workforce_delivery/example_bundle.json \
  --output /tmp/ky-workforce-report.json
```

Exit `0` means the supplied bundle satisfies this engine's operational evidence
contract. Exit `2` means the report contains validation errors. The JSON report is
canonical and includes both the input evidence SHA-256 and a report SHA-256.

Input must be an ordinary regular file. Duplicate JSON object keys are rejected.
Symlinked inputs, aliased input/output paths (including existing hardlinks), and
non-regular output targets fail closed. File output is published via same-directory
temporary file, `fsync`, and atomic replacement.

## Truth boundary

A passing report proves only what the supplied bytes establish against this package's
rules. It does **not** establish the three-year experience gate, three comparable
references, a teaming relationship, named-instructor availability, WIOA/DWG legal or
records compliance, statewide travel commitments, insurance/registration, buyer
approval, pricing acceptance, submission, contract award, or cash. Those remain
separate evidence and owner/partner responsibilities from issue `#13536`.
