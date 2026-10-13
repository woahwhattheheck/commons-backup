# UIOWA-024 — Fictional selection, capacity and evidence-window rehearsal

**Every ID, context, artifact and observation below is invented for this demonstration. No interview occurred. Availability was not checked; no invitation was sent, no University source was accessed, and no finding was established.** These are hand-authored planning scenarios with separately checked set/count arithmetic. They are not results from Quartz-731's unpublished planner.

Read the [field guide](24-sampling-plan.md) before interpreting the [editable matrix](coverage-matrix.md). The target is six to eight distinct people per group; it is not a claim of statistical representativeness. Planned topic labels remain distinct from actual conversation or evidence support.

## 1. Fictional frame

Six required role perspectives apply to each group: `service_owner`, `implementation`, `verification`, `operations`, `consumer_support`, `security_identity`. Technical and delivery requirements are explicitly chosen for this example:

| Group | Required stack/context tags | Required delivery-pattern tags |
| --- | --- | --- |
| ESS | `batch; web_api; managed_identity` | `term_peak; routine_release; access_change` |
| RIS | `research_platform; data_pipeline; shared_identity` | `project_delivery; routine_change; access_change` |
| IAM | `directory; provisioning_connector; managed_identity` | `joiner_mover_leaver; routine_change; emergency_change` |

The same `S01` supports ESS and RIS; the same `S02` supports ESS and IAM. Their perspective tags below are specific to the service row. They are not different people because their service context differs. These fictional planning tags do not prove anyone's actual competence or firsthand experience.

<!-- audit-table: roster -->
| Person | Group | Perspective | Stack/context | Delivery pattern |
| --- | --- | --- | --- | --- |
| E01 | ESS | service_owner | web_api | term_peak |
| E02 | ESS | implementation | web_api | routine_release |
| E03 | ESS | implementation | batch | routine_release |
| E04 | ESS | verification | web_api | routine_release |
| E05 | ESS | operations | batch | term_peak |
| E06 | ESS | consumer_support | web_api | term_peak |
| S01 | ESS | security_identity | web_api | access_change |
| S02 | ESS | security_identity | managed_identity | access_change |
| R01 | RIS | service_owner | research_platform | project_delivery |
| R02 | RIS | implementation | research_platform | routine_change |
| R03 | RIS | implementation | data_pipeline | project_delivery |
| R04 | RIS | verification | research_platform | routine_change |
| R05 | RIS | operations | data_pipeline | routine_change |
| R06 | RIS | consumer_support | research_platform | project_delivery |
| S01 | RIS | security_identity | shared_identity | access_change |
| R07 | RIS | implementation | data_pipeline | project_delivery |
| I01 | IAM | service_owner | directory | joiner_mover_leaver |
| I02 | IAM | implementation | provisioning_connector | routine_change |
| I03 | IAM | implementation | provisioning_connector | joiner_mover_leaver |
| I04 | IAM | operations | directory | routine_change |
| I05 | IAM | verification | managed_identity | routine_change |
| I06 | IAM | consumer_support | directory | joiner_mover_leaver |
| S02 | IAM | security_identity | managed_identity | routine_change |
| I07 | IAM | security_identity | managed_identity | emergency_change |
<!-- audit-end: roster -->

Frame size is **24 person-group rows and 22 people globally**. Its inclusion routes are fictional; no actual nomination independence or frame completeness is established.

## 2. Proposed grouped bundles

All nine bundles are `PROPOSED_NOT_SCHEDULED`, with availability `NOT_CHECKED`. “Week” is a hypothetical relative work phase, not a calendar booking. Every bundle is assumed to last 45 minutes with two assessors. Shared-person conflicts still require checking before invitations.

<!-- audit-table: bundles -->
| Bundle | Group | Week | Minutes | People | Planned topics |
| --- | --- | --- | --- | --- | --- |
| E1 | ESS | 2 | 45 | E01; E02; E04 | software; ai |
| E2 | ESS | 3 | 45 | E03; E05; E06 | software; deployment |
| E3 | ESS | 4 | 45 | S01; S02; E02 | security; deployment |
| R1 | RIS | 2 | 45 | R01; R02; R04 | software; ai |
| R2 | RIS | 3 | 45 | R03; R05; R06 | software; deployment |
| R3 | RIS | 4 | 45 | S01; R07; R02 | security; ai |
| I1 | IAM | 2 | 45 | I01; I02; I04 | software; deployment |
| I2 | IAM | 3 | 45 | I03; I05; I06 | software; ai |
| I3 | IAM | 4 | 45 | S02; I07; I02 | security; deployment |
<!-- audit-end: bundles -->

The repeated implementation participants supply continuity between bundles. That continuity is not independent corroboration. A security conversation alone does not establish the entire security assessment, and an AI agenda entry does not establish observed AI use.

## 3. Full-plan calculation

Select `E1; E2; E3; R1; R2; R3; I1; I2; I3`.

<!-- audit-table: full-counts -->
| Group | Selected bundles | Session appearances | Distinct people | Role perspectives | Stacks | Patterns | Planned topics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ESS | 3 | 9 | 8 | 6 | 3 | 3 | 4 |
| RIS | 3 | 9 | 8 | 6 | 3 | 3 | 4 |
| IAM | 3 | 9 | 8 | 6 | 3 | 3 | 4 |
<!-- audit-end: full-counts -->

There are **27 appearances**, **24 distinct person-group pairs**, and **22 people overall**. The first subtraction is the repeated implementation person within each group; the second removes the cross-group repeat of `S01` and `S02`. Never call these 27 or 24 independent interviewees. Actual participants and actual topic coverage remain unobserved.

Each group meets the proposed six-to-eight target and contains all the declared example dimensions. That is **planned coverage of this fictional frame**, not proof of representativeness, completeness, maturity or a successful assessment.

At a three-bundle weekly capacity, the phase distribution is week 2: 3; week 3: 3; week 4: 3. Total session time is `9 × 45 = 405` minutes (6.75 hours). With two assessors, session-only assessor effort is `810` minutes (13.5 hours). Participant time is `27 × 45 = 1,215` minutes (20.25 hours). Preparation, artifact work and reporting are excluded.

## 4. Scarce capacity: five bundles

Suppose only five bundles can be proposed in the initial round. Retain `E1; R1; I1; E3; R3` to put every group in the first round and preserve two security conversations. This is one documented tradeoff, not a uniquely optimal plan.

<!-- audit-table: limited-counts -->
| Group | Selected bundles | Session appearances | Distinct people | Role perspectives | Stacks | Patterns | Planned topics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ESS | 2 | 6 | 5 | 4 | 2 | 3 | 4 |
| RIS | 2 | 6 | 5 | 4 | 3 | 3 | 3 |
| IAM | 1 | 3 | 3 | 3 | 2 | 2 | 2 |
<!-- audit-end: limited-counts -->

The plan has **15 appearances, 13 person-group pairs and 12 global people**. ESS and RIS are each one person below the minimum of six; IAM is three below. `S01` is shared across two selected groups; `S02` appears only in ESS in this selection.

| Group | Missing role perspectives | Missing stack/context | Missing delivery pattern | Missing planned topics |
| --- | --- | --- | --- | --- |
| ESS | `operations; consumer_support` | `batch` | None within declared set | None within declared set |
| RIS | `operations; consumer_support` | None within declared set | None within declared set | `deployment` |
| IAM | `verification; consumer_support; security_identity` | `managed_identity` | `emergency_change` | `security; ai` |

The unused bundles are `E2; R2; I2; I3`. The next choice should answer the most consequential documented gap, with the reason and capacity tradeoff retained. For example, `I3` introduces security/identity and emergency-change perspectives to IAM, while `I2` introduces verification and consumer support. Neither alone makes the constrained initial round fully covered. Do not simply replace the lowest count with “adequate.”

## 5. Headcount is not coverage: six bundles

A different capacity choice selects `E1; E2; R1; R2; I1; I2`. All groups reach six distinct people, for **18 appearances, 18 person-group pairs and 18 global people**. None of the two shared participants is selected, and no within-group implementation repeat occurs.

<!-- audit-table: six-counts -->
| Group | Selected bundles | Session appearances | Distinct people | Role perspectives | Stacks | Patterns | Planned topics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ESS | 2 | 6 | 6 | 5 | 2 | 2 | 3 |
| RIS | 2 | 6 | 6 | 5 | 2 | 2 | 3 |
| IAM | 2 | 6 | 6 | 5 | 3 | 2 | 3 |
<!-- audit-end: six-counts -->

Every group still lacks the `security_identity` perspective and the `security` topic. ESS lacks `managed_identity` and `access_change`; RIS lacks `shared_identity` and `access_change`; IAM lacks `emergency_change`. The six-person target is met while important dimensions remain missing. These gaps must remain in the report or trigger a targeted change in the proposed bundles.

This contrast is why the field guide keeps counts, perspectives, technical contexts, delivery patterns and agenda topics separate. A single weighted “coverage score” would hide a choice that needs explanation.

## 6. Capacity, repetition and nonresponse checks

**Collapsed-window check.** Moving all nine full-plan bundles into one hypothetical week does not change who is proposed, but exceeds the three-bundle weekly capacity by **six bundles**. It still requires 6.75 session hours; the overload is against the explicitly declared bundle cap, not a universal weekly working-hour limit. Do not silently revise the cap or manufacture confirmed availability.

**Repeated-bundle check.** Entering `E1` twice is a duplicate plan-row error, not an extra selected bundle. A legitimately separate follow-up must have a new session ID and a reason; repeated attendance may increase appearances and workload but not the number of distinct people.

**Nonresponse check.** If the proposed `S01` becomes unavailable, retain both affected service rows and mark that change. Removing `S01` from the full plan yields **25 appearances, 22 person-group pairs and 21 global people**; ESS and RIS each have seven people. ESS still has the security/identity perspective through `S02`, but RIS loses that perspective, `shared_identity`, and `access_change`. Counts remain inside the target while RIS coverage worsens. This is a revised proposal, not actual attendance. Preserve the unavailability reason only at the appropriate privacy level.

**Window check.** A later artifact does not retrospectively fill the original event window. Keep the old question open or explicitly label an approved scope extension; do not change the old snapshot's date to get a more favorable result.

## 7. Fictional artifact follow-through

For this separate illustrative evidence round, the intended **event window is 2026-07-01 through 2026-08-31, inclusive**. A “received” or “read” state below is a fictional scenario input, not a real tool execution or University observation. Placeholder locators beginning `fictional:` are not live links.

<!-- audit-table: artifacts -->
| Request | Group | Topic | Primary state | Fictional source/window and interpretation |
| --- | --- | --- | --- | --- |
| E-SW | ESS | software | IN_WINDOW_READ | fictional:E-release-v1, event 2026-08-12; one selected change chain, not all releases |
| E-SEC | ESS | security | CONFLICT_OPEN | fictional:E-access-v1 vs fictional:E-interview-v1 disagree about the same July revocation; retain both |
| E-OPS | ESS | deployment | PARTIAL_WINDOW | fictional:E-ops-v1 covers only 2026-08-15 through 2026-08-31; July and early August remain unobserved |
| E-AI | ESS | ai | REQUESTED_UNAVAILABLE | Requested inventory not supplied; no-use and readiness conclusions remain unsupported |
| R-SW | RIS | software | IN_WINDOW_READ | fictional:R-review-v1, event 2026-07-21; bounded review metadata only |
| R-SEC | RIS | security | REQUESTED_UNAVAILABLE | Requested account review not supplied; absence of review is not established |
| R-OPS | RIS | deployment | CONFLICT_OPEN | fictional:R-change-v2 and fictional:R-incident-v1 disagree about rollback completion on 2026-08-08 |
| R-AI | RIS | ai | IN_WINDOW_READ | fictional:R-evaluation-v1, event 2026-08-03; one evaluation example, not operational validation |
| I-SW | IAM | software | IN_WINDOW_READ | fictional:I-connector-v1, event 2026-08-04; selected implementation/verification chain |
| I-SEC | IAM | security | OUTSIDE_WINDOW | fictional:I-removal-v1 records event 2026-09-06; it cannot fill the July–August event window |
| I-OPS | IAM | deployment | IN_WINDOW_READ | fictional:I-followup-v1, event 2026-07-29; selected recovery follow-up |
| I-AI | IAM | ai | REQUESTED_UNAVAILABLE | An interview assertion of no use is retained separately; inventory scope is not established |
<!-- audit-end: artifacts -->

State counts are **five `IN_WINDOW_READ`, two `CONFLICT_OPEN`, one `PARTIAL_WINDOW`, one `OUTSIDE_WINDOW`, and three `REQUESTED_UNAVAILABLE`**. There are twelve requests. Nine have a fictional supplied source of some kind; only five are described as in-window read, and even those five do not automatically support a favorable conclusion. Do not turn `5/12` into a readiness score or call the other seven proven practice failures.

The following follow-ups preserve all seven primary limitations rather than discard difficult examples:

| Follow-up | Request | Unresolved proposition | Proposed evidence or action | Initial disposition |
| --- | --- | --- | --- | --- |
| F01 | E-SEC | Whether the identified July revocation completed when claimed | Retain the exact event/identity/version mapping and ask for the corresponding completion record | OPEN |
| F02 | E-OPS | What the missing July–early-August portion can show | Request bounded export coverage or explicitly narrow the statement to August 15–31 | OPEN |
| F03 | E-AI | Whether an adequately scoped AI-use inventory is available | Clarify the inventory owner, scope and alternate source; do not infer no use | OPEN |
| F04 | R-SEC | Whether a scoped review record exists and can be inspected | Request the bounded review source or record unavailable evidence | OPEN |
| F05 | R-OPS | Whether the selected rollback completed | Preserve both references, identify their version/event relationship and obtain the completion trace | OPEN |
| F06 | I-SEC | Whether the requested in-window event evidence exists | Request in-window evidence or carry a separately labeled later contrast | OPEN |
| F07 | I-AI | What supports the no-use assertion and its scope | Clarify coverage and retain the assertion as an account until supported | OPEN |

## 8. Ready-to-use report language

> The proposed fictional plan includes eight distinct participants per group and twenty-two people overall, with repeated participation counted separately. It covers the example's declared role, technical-context and delivery-pattern sets on paper. Availability, actual attendance and actual topic coverage are not established. This purposeful design supports targeted inquiry; it does not establish statistical representativeness.

> In the separate fictional artifact round, five selected records are described as read within the event window. Two conflicts, one partial window, one later event and three unavailable requests remain explicit. Those limitations guide follow-up and statement scope; they are not evidence that the underlying practices are absent or defective.

> Under a five-bundle capacity alternative, the group counts become five, five and three. A six-bundle alternative reaches six people in every group but omits all three security/identity perspectives. The selection decision therefore requires an explicit coverage tradeoff rather than a headcount-only pass.

## 9. Validation and provenance

The source tables are ordinary editable documentation. Audit markers identify the roster, bundles, three expected count tables and artifact states; they do not execute anything. HARBOR-C9V2's retained checker reads those tables, recomputes the distinct sets and workload, and compares each scenario's expected counts and gaps. The checker and literal normal/optimized result are published on the delivery PR as supporting review material, not hidden in a chat-only workspace.

The checks cover unique person-group keys; session membership; duplicate bundle refusal; all three count scenarios; exact missing perspectives/contexts/patterns/topics; shared-person nonresponse; workload arithmetic; weekly overload; artifact-state totals; seven follow-up references; local document links; and the six-to-eight target distinction. Passing those checks validates the example's internal consistency, not a real interview, frame completeness, source authenticity, inference, or the unavailable original planner.

Original grouped-session direction: Quartz-731. Field kit, editable matrices and this separately authored fictional rehearsal: ZZ-HARBOR-C9V2 / GPT-6 Astra Pro, operation `uiowa024-fieldkit-harborc9v2-20260919`.
