# AI lifecycle interview and investigation worksheet

**UIOWA-079 preparation instrument.** Complete at workflow/team level; do not
score individual staff. The worked examples are fictional. Leave actual
University answers unknown until the relevant participants and artifacts supply
them. This worksheet does not recommend a commercial AI product or authorize a
system change.

## A. Establish a useful workflow boundary

Record the workflow ID, organizational group, purpose, input population,
user-visible output, integration points, typical frequency, and accountable
support role. Ask the team to select a recent meaningful change rather than
reciting an ideal policy. State what is excluded: other AI experiments, other
model endpoints, different task populations, and unobserved usage.

| Question to explore | Metadata/evidence to request | What remains unknown without it |
|---|---|---|
| What exactly changed? | Parent and candidate version IDs, change timestamp/reason, model revision, prompt/configuration/code/source-snapshot identifiers | Which component or combination changed |
| Could this same input be investigated later? | Retained input snapshot, locator, digest, retention owner; no credential values | Whether later investigators can reconstruct the context |
| What was actually evaluated? | Versioned case manifest, case input/expected-answer digests, protocol, rubric and evaluator-calibration notes | Comparability, coverage and interpretation of scores |
| Which run produced the observation? | Explicit run IDs, timestamps, per-case outputs, scores, errors and units | Whether a result was measured, inferred or copied from another run |
| Did support see the same behavior? | Version-bound incident records, affected task class, investigation references, accountable role and action | Connection between test results and operational experience |
| What would replay demonstrate? | Two same-version run IDs, retained output bytes and exact/tolerance criterion | Whether output identity or only functional usefulness was assessed |
| Who maintains this after the update? | Role handoff, escalation route, artifact retention responsibility, open follow-up | Operational continuity rather than individual capability |

Record interview testimony separately from retained artifacts. A policy is
stated intent; a digest/locator is an evidence reference; a linked run record is
supplied observation. None is automatically an independently verified finding.

## B. Conduct a reproducible tabletop

Use `synthetic.py` and run the commands in the README. Preserve the input and
three exported formats with the operation/revision. The reviewer should perform
these tasks against the real generated report, not a narrative recollection.

| Task | Expected result in the fictional fixture | Follow-up when reviewing actual evidence |
|---|---|---|
| Follow baseline v1 to its repeated output | `baseline-repeat` matches retained output bytes in 4/4 cases | Can the team preserve original input/configuration and output evidence? |
| Explain the v2 change | Both `model` and `prompt` changed; model revision also changed | Isolate changes in a controlled rerun before claiming a single cause |
| Find the missing v2 observation | c4 has a timeout, unknown quality scores, and no output reference | Determine error scope and retain error context; do not impute a zero |
| Read the regression denominator | Correctness comparison is 3 paired cases out of 4 expected | Obtain the missing observation or explicitly limit the interpretation |
| Check whether the repair solved everything | Correctness improves on the paired subset; latency worsens 100 ms | Select measurable quality and time tradeoffs with the service owner |
| Distinguish functional from exact replay | v3 quality scores match, but repeated c2 output bytes differ | Agree whether exact bytes, a tolerance, or a rubric is relevant to the task |
| Compare v3 with v4 | Evaluation definition changed; no numerical delta is emitted | Re-evaluate both versions on the same retained definition if useful |
| Trace incident1 to its resolution | `resolution1` belongs to v3 and links recorded repair evidence | Confirm closure criterion and whether recurrence was observed |
| Find the unresolved continuity problem | incident2 remains open; v4 lacks support and retention evidence | Establish a team role and gather current records; do not infer a production defect |

## C. Proportionate improvement options

These are **planning hypotheses**, not commitments, observed University gaps,
or promised staffing capacity. Discuss actual collection effort and dependencies
before using any range in a roadmap. Days below are relative planning buckets,
not booked meetings or deployment schedules.

| Trigger from evidence | Practical improvement and role | Dependencies and effort hypothesis | Observable outcome / next evidence |
|---|---|---|---|
| Version can only be named by a mutable alias | Application-support role records the provider revision/manifest, prompt and configuration at change time | Existing change record access; roughly 0.5–1 analyst day to trial a template on one workflow, then measure recurring effort | Next sampled change has inspectable component references; provider immutability remains explicitly bounded |
| Evaluation history omits case input/expected-answer identity | Evaluation owner introduces the case manifest and versioned rubric | Agreed task boundary and permitted retained metadata; 1–3 analyst/developer days for one pilot | Editing an input/answer/protocol changes the manifest and comparison becomes explicitly incomparable until rerun |
| Errors or missing scores disappear from summaries | Evaluation owner retains expected denominators, nulls and per-case errors | Existing runner/export can distinguish zero from unknown; 0.5–2 developer days | Pilot report visibly includes timeout/missing cases and paired subset coverage |
| Multiple components changed and a gain is attributed to one | Workflow owner designs a controlled comparison where practical | Same retained case set/rubric; provider version availability; effort depends on existing evaluation execution | Report lists changed factors and makes only claims supported by that comparison |
| Better scores mask worse latency or repair effort | Service owner includes time/repair measures in the review | Agreed units, baseline task population and sampling; 1–2 analyst days to define a pilot | Quality and operating-effort deltas are read together, including tradeoffs |
| Incident closure has no linked follow-up record | Support role connects investigation, run and resolution identifiers | Existing support process and permitted evidence retention; 0.5–1 analyst day on one example | A reviewer can follow the incident through resolution evidence without reconstructing provenance manually |
| Support/retention ownership is missing | Team lead records the role handoff and artifact retention responsibility | Identify responsible group; clarify existing policy rather than inventing one; effort to be measured during pilot | Later reviewer locates a current role and the agreed artifact set |

Adoption of a template is an activity, not a reliability result. Track separately:
records collected, collection minutes per sampled change, fraction of sampled
changes reconstructable from retained evidence, time to investigate a selected
question, repeated unresolved incident conditions, and measured output quality
on the agreed case population. Preserve sampling period/denominator; do not
convert these measures into employee rankings or unsupported benefits.

## D. Reviewer decision record

Copy this block into the existing assessment evidence register or local notes:

```text
Workflow / group:
Version pair and named run IDs:
Question being assessed:
Input/evaluation/rubric identifiers and locators:
Supplied observations versus interview statements:
Expected / paired / missing cases per metric:
Recorded component changes and confounders:
Runtime event and investigation IDs:
Reproduction evidence status and limitations:
Supported statement (bounded to observed scope):
Contradictory evidence or alternative explanations:
Unresolved evidence and collection role:
Proposed improvement, dependencies and effort assumptions:
Success measure, denominator and collection burden:
Disposition: retain / revise / gather evidence (not deployment approval)
```

For the fixture, a defensible statement is: “On three paired fictional cases,
the recorded correctness score improved after v3, while latency increased and
exact wording varied in a repeat.” An indefensible statement is: “The University
AI workflow improved by 66.7% and is now reproducible.” The fixture cannot
establish either University behavior or future deterministic execution.
