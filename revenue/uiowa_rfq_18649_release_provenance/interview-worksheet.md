# Release provenance interview and evidence worksheet

UIOWA-057 · reusable preparation instrument · **no institutional findings**

## Sample boundary

Service / group: ____  Reviewer role: ____  Evidence period: ____
Ordinary release ID: ____  Exception or recovery release ID: ____
Selection rationale and exclusions: ____  Original record custodian: ____
All source locators and existing handling restrictions: ____

A manual record can be adequate if it is precise, retrievable and demonstrated. Automation alone is not maturity. Assess the organizational practice, not an individual employee's competence. This is a process assessment, not a formal compliance audit, penetration test, or product-purchasing exercise.

## Evidence-chain matrix

| Link | Request existing evidence | Interview demonstration | Interpretation / follow-up |
|---|---|---|---|
| Approval → source | Change record, repository identity, full approved revision, timestamp, custodian | Find the approved revision for the sampled release; show how changes after approval are handled | A policy describes intent. A source-specific record plus an observed retrieval example supports a narrower practice finding. Missing records remain unknown. |
| Source → build attempt | Attempt ID, actual repository/revision, recipe identity, builder label, start/end times | Distinguish a failed attempt, a rerun and the attempt producing the released artifact | A matching revision without matching repository identity is insufficient. Different attempts must not be silently merged. |
| Build → inputs | Resolved toolchain/dependency/configuration input identifiers and digests; capture boundaries | Identify what was captured, generated dynamically, omitted, or inherited | Declared completeness is not demonstrated completeness. Ask about relevant external inputs without requesting credentials or secret values. |
| Build → artifact | Output digest, artifact custodian, artifact version, retained copy, producing attempt | Retrieve the precise output rather than rebuild a replacement | Matching metadata proves agreement of records only. Optional byte hashing binds the supplied copy, not builder authenticity. |
| Artifact → deployment | Existing deployment observation, exact digest, environment, observed time, deployment record locator | Find which artifact was observed in the selected environment and distinguish it from a planned release | A human-friendly version label may be reused. Digest and label disagreements are separate reconciliation questions. |
| Retention → retrieval | Retention practice, ownership changes, access arrangements, recovery example | Another authorized practitioner retrieves the same sample after a handoff | A written retention period is not proof of retrieval. Document actual elapsed effort and missing links without inventing performance targets. |

## Record findings with appropriate strength

For each sampled release retain: record IDs; original locators; stated practice; observed retrieval; supplied artifact/metadata; evidence period; disagreements; scope limits; consequence; follow-up owner role; and the next request. Describe `LINKED_RECORDS` as internally consistent supplied metadata, `GAPS` as unresolved links or values, and `CONTRADICTORY_RECORDS` as records requiring reconciliation. Neither an aggregate code nor a count of missing fields is a maturity rating.

Synthetic example A supports: “Within this fictional packet, deployment d1 links to a1, b1 and s1; two input digests are recorded. The provided artifact copy matches its recorded digest.” It does not support: “All releases are verified,” “the builder is trusted,” or “the institution meets SLSA.”

Synthetic example B supports: “The provided export omits b1, preventing a source-to-build-to-artifact trace.” Ask whether b1 exists elsewhere and whether its retrieval is repeatable. Keep “not supplied” distinct from “does not exist.”

Synthetic example C supports: “Artifact and deployment digest fields disagree.” First preserve both records, then ask which observation, packaging step or label is represented. A discrepancy does not by itself establish an unauthorized change or compromise.

## Practical improvement options

The effort bands below are **planning hypotheses**, not estimates for a real team. Replace them after evidence review. All options reuse existing tools and accountable organizational roles; none mandates a commercial product.

| Observed pattern to confirm | Practice option | Dependencies / responsible role | Illustrative effort and ongoing cost | Observable next step |
|---|---|---|---|---|
| Custodians cannot find source-specific release records | Add common release and attempt identifiers to existing records and document their locations | Agree naming across development and operations; service delivery owner | 0.5–2 staff-days setup; 10–20 minutes per sampled release initially | A second practitioner retrieves the complete ordinary-release chain using only documented locators. |
| Inputs are only partially captured | Define the relevant input inventory boundary and capture resolved identifiers in the existing build record | Understand build steps; build-platform maintainer | 2–5 staff-days investigation/adapter work; periodic checks after recipe changes | A rehearsal distinguishes captured, externally resolved and unknown inputs without marking unknown as complete. |
| Deployment record retains only a mutable label | Preserve the observed artifact digest beside the label in existing deployment records | Available artifact identity and deployment metadata; operations owner | 1–3 staff-days adapter change; maintenance when deployment format changes | Two versions with the same label are distinguishable by recorded identity; one ordinary release is traced end to end. |
| Handoff breaks record retrieval | Add a bounded release-record retrieval exercise to an existing service handoff | Existing access arrangements and retention responsibilities; service owner | 0.5–1 staff-day exercise; repeat after ownership or tooling changes | A new custodian recovers a selected older release and explicitly identifies any retained gaps. |

## Follow-up disposition

Question: ____  Evidence requested: ____  Accountable role: ____
State: open / corroborated / contradicted / outside sampled scope / unresolved
Original packet version: ____  Corrected packet version: ____
What changed, and why: ____  Findings affected: ____

Do not schedule interviews, approve releases, change retention, alter access, or contact external parties by running this kit. Those are separate organizational actions. No calendar action is embedded in the tool.
