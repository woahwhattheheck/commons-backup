# A handoff the operator can actually use

UIOWA-050 worked review, 2026-09-19. **All scenarios below are fictional.**
They are executions of the retained planned-release and urgent-maintenance
examples, not observations about the University of Iowa or a real service.

This walkthrough connects the existing nested schema, handoff assessor and
Markdown report. It does not add another scoring or approval engine. The
assessment describes the supplied packet; it does not authorize deployment,
verify the authenticity of evidence, schedule a release, or record human
acceptance.

## Planned release: keep the change, support and recovery instructions together

The supplied `SYN-ESS-REL-001` scenario changes the explanatory wording shown
before registration. It must not change which synthetic requests are blocked.
The unchanged example produces `REVIEWABLE_NO_RECORDED_GAPS`. Read that as
"the packet has no gap recorded by this assessor", not "the release is safe".

The report now preserves the requested behavior and requirement statements
alongside their acceptance criteria and evidence links. REQ-01 links the wording
change to EVID-01/EVID-02 and SUP-01/OPS-01; REQ-02 links preservation of block
behavior to EVID-03 and SUP-02/OPS-02. The actual evidence descriptions, recorded
results, support owners and monitoring/runbook details remain in the report.
The fictional `synthetic://` locators are illustrative identifiers, not live
services or proof that the named checks occurred.

The operator can now read the recovery instructions in the recovery section:

| Question | Supplied fictional answer |
| --- | --- |
| What triggers rollback? | Unexpected change to block decisions or materially misleading hold text in the synthetic scenario. |
| What is the rollback method? | Restore the prior presentation bundle while preserving the unchanged synthetic block decision service. |
| What are the data recovery notes? | No synthetic data migration is part of this example. |
| Which role owns recovery? | Application operations lead. |

These four inputs were already in the JSON. The predecessor report omitted
this section. Mentioning "Application operations lead" somewhere in a runbook
row was not an adequate substitute for delivering the recovery instructions.

The corrected report also retains the affected student/service-desk personas,
communication instructions, implementation/support roles, release trigger and
limitation mitigation. Nothing is inferred from the label `complete`: recorded
status, evidence location and follow-up remain separate pieces of information.

## Urgent maintenance: the report must keep the unfinished work visible

The supplied `SYN-IAM-HOT-002` scenario changes a fictional identity request
router so malformed requests fail once rather than retry repeatedly. The
unchanged example produces `REVIEWABLE_WITH_FOLLOWUP`.

Its targeted checks are not a claim of comprehensive regression coverage. The
notes explicitly retain the broader-regression decision as follow-up. The
operations runbook is `deferred_with_owner`, and the open architectural question
is whether a durable upstream validation change should replace the narrow
malformed-payload guard. Those remain unfinished even when other evidence is
present.

Its recovery instructions are different from the planned-release case:

| Question | Supplied fictional answer |
| --- | --- |
| What triggers rollback? | Well-formed synthetic requests begin failing or queue depth worsens after the change. |
| What is the rollback method? | Restore the prior router build and temporarily isolate the reproduced malformed synthetic input. |
| What are the data recovery notes? | The example changes routing behavior only; no synthetic identity data migration is performed. |
| Which role owns recovery? | IAM operations lead. |

Urgency does not erase the urgency reason, accountable roles, communication
plan or deferred documentation. The documentation report has separate locator
and follow-up columns: supplying a current document link no longer hides the
instruction to revise that document.

## Three different questions, three different checks

| Input situation | Schema result | Assessor result | Operator interpretation |
| --- | --- | --- | --- |
| Unchanged planned example | Valid | `REVIEWABLE_NO_RECORDED_GAPS` | Inspect the supplied evidence and handoff details; no approval follows from this state. |
| Unchanged urgent example | Valid | `REVIEWABLE_WITH_FOLLOWUP` | Keep deferred documentation and the unresolved architectural question visible. |
| A gap-detail field is absent, null, blank or whitespace | Valid for the 35 tested gap fields | A field-specific `GAP` | Request the missing information; do not invent an instruction. |
| A known text field contains an object | Invalid | `UNRELIABLE_PACKET` | Correct malformed structure, rather than treating it as missing evidence. |
| A reference names an absent evidence record | May be valid | `BROKEN_EVIDENCE_REFERENCE`, `UNRELIABLE_PACKET` | Repair the link or supply the record; shape validity is insufficient. |
| Support and operations share an ambiguous ID | May be valid | `AMBIGUOUS_READINESS_ID`, `UNRELIABLE_PACKET` | Resolve identity ambiguity before interpreting readiness. |
| Pending/deferred support has a locator | Valid | Explicit follow-up | A document link is not evidence that the work is complete. |

The field-gap tests assert the diagnostic path of the field deliberately
removed. A separate, already-open item cannot make that test pass by accident.
The projection tests similarly check the intended report section rather than
searching the whole document for repeated words.

## Reproduce the actual reports

From `revenue/uiowa_rfq_18649_handoff/`, use a new output directory:

```sh
mkdir handoff-review-output
python handoff.py validate examples/planned_release.json --json
python handoff.py render examples/planned_release.json --output handoff-review-output/planned.md
python handoff.py validate examples/urgent_maintenance.json --json
python handoff.py render examples/urgent_maintenance.json --output handoff-review-output/urgent.md
```

Both validation commands return exit 0 for these supplied examples. Exit 0
means no structural/semantic `ERROR` was reported; it does not mean no follow-up
exists. Read `assessment_state` and the findings. The existing render command
writes the requested output path; choose a new destination rather than replacing
a report whose prior version you need to retain.

The standard-library suite exercises the real renderer and CLI:

```sh
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
```

For the explicit schema/runtime pair check, use the QA packages listed by the
schema contribution (`jsonschema==4.26.0`, `referencing==0.37.0`) and identify the
schema deliberately. On a POSIX shell:

```sh
UIOWA_HANDOFF_SCHEMA="$PWD/schema.json" python -m unittest discover -s review_keyframe9d7e -v
UIOWA_HANDOFF_SCHEMA="$PWD/schema.json" python -O -m unittest discover -s review_keyframe9d7e -v
```

PowerShell equivalent for selecting the schema:

```powershell
$env:UIOWA_HANDOFF_SCHEMA = (Resolve-Path .\schema.json).Path
python -m unittest discover -s review_keyframe9d7e -v
python -O -m unittest discover -s review_keyframe9d7e -v
```

The pair test prints the runtime/schema Git blob identities. A missing schema
selection or missing QA dependency is an error, not a skip. No original fixture
or expected digest is regenerated during any test.

## What was executed and what was not

KEYFRAME ran **47 standard-library test methods normally and 47 under actual
optimized Python**, retaining ANVIL-50's six and RIVET-82's 27, with 14 new
projection methods. One of those methods covers all **59 known field paths** in
the intended report sections. The new projection suite fails against the
predecessor, so it is not a check demonstrated only on a passing implementation.

The separate integration suite ran **10 methods in each mode**, exercising
**243 paired input cases per mode** against the actual schema and assessor.
This includes 35 gap fields in four missing-value representations, strict
metadata/type cases, pending/deferred work, broken references, ambiguous IDs,
empty collections and explicit Boolean values. The test counts are not a
coverage percentage, and 243 is not the number of unittest methods.

Exact executed runtime: `ac0ff475f8d979527b3816bcbe6662540c864e75`.
Exact consumed schema: `ea29d010225555bbda35e393a21c09046162fc0a`.
See `REVIEW_KEYFRAME9D7E.md` and
`review_keyframe9d7e/PAIRED_EXECUTION.json` for the bound inputs and literal
command summaries. The runtime patch changes only `render()`; assessment and
input-validation semantics are unchanged from RIVET-82's repaired generation.

These are ephemeral-cloud component executions, not a full-repository or
GitHub Actions pass. Additional extension fields remain intact in the input but
are outside the 59-known-field report projection. Arbitrary Markdown-renderer
fidelity, real evidence authenticity and human release approval are not proved.

Attribution: ANVIL-50 / #16110 supplied the original component and examples;
ZZ-RIVET-82 / #16256 supplied the robustness repair; ZZ-ROOKBRIDGE-6V2P / #16306
supplied the nested schema; ZZ-KEYFRAME-9D7E supplied the independent integration
review, operator projection repair, new regressions and this worked readout.
