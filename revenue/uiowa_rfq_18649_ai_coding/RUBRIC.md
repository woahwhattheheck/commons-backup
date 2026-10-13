# Workflow evidence rubric and interview worksheet

**Proposed method; all examples fictional.** This rubric assesses a delivery practice, not a person. The state labels are descriptive categories, not a numerical maturity scale. Manual and AI-assisted changes face the same outcome questions.

## Observable anchors

| Criterion | Directly supported practice | Evidence of a specific gap | Useful next question |
|---|---|---|---|
| Understanding | A walkthrough ties changed behavior and assumptions to the request, including boundaries and dependencies. A maintainer can explain the accepted revision. | The retained walkthrough demonstrates a mistaken assumption that affects behavior, or a handoff explicitly leaves changed logic unexplained. | Which assumption did the generated draft make? Show the accepted revision and an example that would invalidate it. |
| Verification | Acceptance rules link to checks with known coverage; boundary and failure cases have explained outcomes; changed checks are rerun against the retained revision. | A concrete acceptance condition was omitted or failed without resolution; a passing check tests a different revision or narrower behavior than claimed. | What does this passing check establish, and what does it not establish? Show one boundary example and the version tested. |
| Revision | Feedback, rejected suggestions, repair work and reruns remain traceable to the same change and requirement. | Records demonstrate unresolved substantive feedback, untracked repair, or a repair that did not receive the necessary checks. | What was rejected or repaired after the first draft? Which reviewer and support effort was included, and where was it allocated? |
| Integration | Functional acceptance, accepted revision, support ownership and handoff are connected rather than inferred from code generation or an approval click. | A retained handoff or acceptance record explicitly identifies a missing support dependency or unmet behavior. | Who owns the behavior after delivery? What evidence links the accepted artifact to the supported service? Use roles, not individual ratings. |
| Maintenance | A bounded observation window has enumerated support records, fault counts, repair effort and an identified maintenance role. | Concrete later support work exposes recurring misunderstanding, missing checks or unmanaged maintenance dependencies. | What happened after acceptance, over what interval, with what reporting coverage? What remains outside that window? |

`demonstrated` means the supplied conclusion has directly linked support for human review; it is not a programmatic verdict that a prose claim is true. `gap` means directly supported evidence of a **specific** shortfall, not an absent document. `stated` is an interview assertion awaiting direct corroboration. `unknown` is unresolved or absent support. `not_applicable` requires a retained scope rationale; it must not hide an inconvenient outcome. `disputed` keeps an explicit disagreement visible with competing sources and a follow-up question. The tool preserves the claimed state and downgrades unsupported demonstrated/gap/not-applicable/disputed assertions to stated or unknown. It does not invent a reconciliation or average the states.

## Reusable interview record

Copy this block for each sampled change. Use role/team descriptions without employee evaluation.

```text
Change ID / component namespace / retained revision:
Service scope and task boundary:
Assisted or manual; what assistance actually occurred:
Request and functional acceptance rule:
Model/context/tool versions or explicit UNKNOWN:
Roles supplying understanding, review, integration and maintenance evidence:
Evidence IDs, full-file hashes, locators, observed dates:
For each criterion: claimed state / exact supporting or dissenting excerpt / effective state:
Allocated person-minutes by stage; uncovered work and possible double allocations:
Accepted timestamp and evidence, or explicit UNKNOWN:
Follow-up start, end, collection coverage, fault definition and severity:
Manual comparison task; matching context; important unmeasured differences:
Concrete follow-up request / owner role / decision it would inform:
Assessor interpretation and limits (separate from participant statement):
```

Ask for a recent concrete example, not only the team policy or preferred workflow. Trace the same change end to end before moving to another. Preserve disagreement about what happened; separate different revisions, services or observation periods before labeling it a contradiction. Avoid requesting actual code, secrets, personal data or proprietary prompts when a redacted process record establishes the point.

## Facilitated synthetic cases

**ESS: faster drafting with retained delivery evidence.** Open the ESS pair in the generated report. Both histories use the same task fingerprint and declared context. The assisted authoring stage is 8 person-minutes versus 75; full lifecycle is 80 versus 150, with zero recorded faults in the same complete 30-day window. Trace `EV-ESS-A-AUTHOR`, `EV-ESS-A-ACCEPT` and `EV-ESS-A-FOLLOWUP`. Supported reading: this fictional record set has lower full-workflow effort with equal recorded fault counts. Unsupported reading: AI will save the University this amount or every unobserved defect is absent.

**RIS: generation speed conceals repair and later maintenance.** Drafting is 5 versus 50 minutes, but full lifecycle is 260 versus 170. Follow `EV-RIS-A-UNDERSTANDING-PRACTICE`, `EV-RIS-A-VERIFICATION-PRACTICE`, `EV-RIS-A-REPAIR` and `EV-RIS-A-FOLLOWUP`. The original empty-field assumption was wrong; repair and maintenance consume the apparent initial gain. Ask which prompt/context or acceptance-rule change might reduce the recurring work, and what evidence would test that explanation. Do not assume the model alone caused the difference.

**IAM: an attractive four-minute draft cannot establish a successful outcome.** The assisted task is broader than the manual one. Test effort, acceptance, follow-up and fault counts are incomplete. The claimed understanding is interview-only. Open the comparison reasons and the `stated` understanding row. Appropriate next requests: bounded task definition, actual acceptance evidence, complete stage allocations, and a mature observation window. Inappropriate result: calling the missing values zero, applying a favorable percentage or rating the team poorly because our evidence is incomplete.

## Designing a supportable improvement study

Before a real comparison, state the task population, eligibility and sampling rules, accepted behavior, observation period, fault/exposure definitions, complete effort boundaries, task/stack/criticality context, and how assisted/manual records will be matched. Record rejected drafts, review and repair work, not only successful outputs. Preserve comparable no-assistance alternatives and failed/abandoned cases to reduce survivorship bias. Include review depth and maintainer experience as contextual explanations without ranking people. Separate measured outcomes from participant impressions and proposed explanations. Report the small sample and its selection limits; do not make causal, financial or institutional claims that the design cannot establish.
