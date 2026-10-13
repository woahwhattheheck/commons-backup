# Environment consistency: facilitator packet and reusable worksheet

**UIOWA-061 · proposed assessment method · ZZ-BASALT-61 / GPT-6 Astra Pro**

Every service, version, topology, evidence item and result in this exercise is fictional. This packet is usable without running software. It does not describe University practice, authorize an environment change, or recommend a purchase. The companion [synthetic environment matrix](synthetic-report.md) is the worked answer sheet. The executable implementation is separately tracked in Commons PR #16168; its publication does not mean hosted execution clearance.

## What the exercise produces

A reviewer leaves with an environment comparison that distinguishes a necessary difference from an unexplained one, identifies the exact evidence still needed, and proposes proportionate follow-up with ownership and effort assumptions. The objective is not to make every environment identical. A reduced test environment, a development-only mock, and a deliberately different compatibility target can be useful when their limits are understood.

Prepare an unfilled copy of the worksheets below. Read the fictional records and classify them before consulting the answer sheet. A second reviewer should be able to reconstruct every conclusion from the same record IDs and dates. Any disagreement is retained with a focused question; it is not settled by averaging opinions.

## Evidence vocabulary

**Observed value** means a supplied record reports the value and points to an artifact. The artifact's existence, authenticity, scope and date still require review; an ID alone is not proof. **Statement** means an interview or recollection that has not been corroborated. **Unknown** means the available evidence does not support the needed conclusion. **Not applicable** requires a reason tied to a particular service and environment; it is not an empty cell or an exemption from all testing.

The example uses September 19, 2026 as its explicit assessment date and fourteen days as its snapshot-age assumption. Neither is a universal standard. Agree a purpose-appropriate evidence window for the real assessment rather than copying this number. A record exactly fourteen days old is within this example's window; a record older than that is not current for comparison. A documented intentional difference has its own validity and review dates, separate from snapshot age.

Four fictional source records are supplied:

| Source ID | Class | Captured | Supplied locator | Meaning in the exercise |
|---|---|---|---|---|
| E-current | Artifact | 2026-09-18 | synthetic/environment-export#current-table | Current settings table; its fictional values are reproduced in the answer sheet. |
| E-old | Artifact | 2026-08-01 | synthetic/environment-export#current-table | Older settings table, outside the example's snapshot window. |
| E-statement | Statement | 2026-09-18 | synthetic/environment-export#current-table | A recollection of the setting, not an observed current artifact. |
| E-rationale | Artifact | 2026-07-01 | synthetic/change-record#intentional-differences | Fictional purpose/constraint records with separate review dates. |

These locators label the synthetic exercise, not retrievable University files. `E-not-supplied` is intentionally unresolved. Do not repair that missing reference by inventing a source.

## Reusable intake worksheet

Use one row per service, setting or dependency, and environment. Capture only nonsecret configuration metadata. Do not request tokens, passwords, personal records or production datasets. A hash of a sensitive low-entropy value does not make it anonymous.

| Field | Entry to collect | Follow-up when missing |
|---|---|---|
| Service and organizational scope | Group, service name and relevant business behavior. | Which service or workflow is actually covered? |
| Environment and purpose | Development, test, staging or production; local purpose and constraints. | Is this a functional, compatibility, integration or capacity test environment? |
| Property under comparison | Setting, component version, provisioning input or configuration reference, with units/type. | Could similar labels describe different things? |
| Recorded value and state | Exact value, explicitly unknown, or non-applicability with reason. | What current artifact would establish the state? |
| Reference environment | Chosen baseline and why it is a useful comparison. | Is an alternative baseline or behavior-based test more appropriate? |
| Source and exact locator | Source ID, version/date and table/section/row locating the observation. | Can another reviewer locate the same evidence? |
| Observation date and scope | Date represented by the snapshot, capture method and known exclusions. | Was this a contemporaneous full observation or a partial/stale export? |
| Provisioning and dependencies | Nonsecret configuration/build reference, inherited services and manual steps. | Can the relevant environment be reconstructed from records? |
| Intentional difference | Both expected values, purpose, accountable role, effective date and review date. | Does the explanation still match the current baseline? |
| Behavior and consequence | Relevant test/incident record or explicitly labeled consequence hypothesis. | What evidence links the difference to actual behavior? |
| Next action | Specific evidence request or improvement, proposed role, effort range and dependency. | Can the question be answered without a broad new data request? |

## Reusable environment matrix

The four columns below do not imply that every service must have four distinct deployed environments. Document actual topology. Shared environments, omitted stages and development-only components remain visible.

| Service / property | Development | Test | Staging | Production/reference | Evidence IDs and dates | Interpretation / open question |
|---|---|---|---|---|---|---|
| [service and typed property] | [value/state] | [value/state] | [value/state] | [value/state] | [source + exact locator] | [supported conclusion or unknown] |
| [dependency and version] | [value/state] | [value/state] | [value/state] | [value/state] | [source + exact locator] | [supported conclusion or unknown] |
| [provisioning reference] | [value/state] | [value/state] | [value/state] | [value/state] | [source + exact locator] | [supported conclusion or unknown] |

Equal strings do not prove equal effective configuration or functional behavior. Different values do not prove a fault. Preserve type and unit differences instead of silently coercing them: boolean `true`, integer `1`, decimal `1.0` and text `"1"` can carry different configuration meanings.

## Classification procedure

First establish whether the target observation has a current artifact reference. Missing, stale, statement-only or explicitly unknown observations remain **UNKNOWN**, even when their displayed value matches production. Record any missing baseline evidence too.

A current, supported reason that the property does not apply to the target is **NOT APPLICABLE**. An observed target with a current, supported non-applicable baseline is **NOT COMPARABLE**; find another reference rather than manufacturing a production value.

When both relevant values are current and comparable, equal typed values are **ALIGNED**. Different values require a purpose/constraint record binding both target and baseline. Exactly one current supported record gives **INTENTIONAL DIFFERENCE**. An otherwise matching record past its review date gives **EXPLANATION REVIEW DUE**. No applicable supported explanation gives **UNEXPLAINED DIFFERENCE**, not a defect verdict. Several competing current explanations remain **UNKNOWN** until reconciled.

Do not turn these categories into a maturity score, error rate or deployment permission. Report a denominator: how many comparisons had enough current comparable evidence, and how many were unknown, non-applicable or not comparable. A single missing baseline can create several affected rows but is still one shared evidence request.

## Three fictional service discussions

### ESS: compatibility purpose and an overdue explanation

The development runtime is version 2, while the current production runtime is version 3. Record R-runtime explicitly describes the 2-versus-3 compatibility exercise, is owned by a test-environment maintainer role, and is valid through October 1, 2026. The supplied-record result is **INTENTIONAL DIFFERENCE**. Ask which compatibility behavior is being exercised and what the environment cannot establish about the production runtime; do not automatically upgrade it to make the table green.

The development database is version 15 while production is 16, with no matching explanation: **UNEXPLAINED DIFFERENCE**. The staging database has the same 15-versus-16 difference but record R-db-expired was due for review on September 1: **EXPLANATION REVIEW DUE**. These rows have the same visible values but different evidence histories. A reasonable initial action is to establish purpose and review the inherited explanation, not immediately rebuild both environments.

The worker-count reference in production was not supplied. Three nonproduction values therefore remain **UNKNOWN** against that reference. Request the missing production observation once and link it to all three rows. Do not count three independent control failures or triple the estimated effort.

### RIS: type differences and recollection presented as parity

The queue flag in development is integer 1 while production reports boolean true. The types differ, so the supplied records show an **UNEXPLAINED DIFFERENCE**. A useful follow-up is whether the consuming configuration parser treats these as equivalent and which test demonstrates that behavior. Do not assert that the service is broken simply because the representations differ.

The provisioning image label is r2 in each displayed environment. Development cites E-not-supplied and test is supported only by E-statement. Both remain **UNKNOWN** despite apparent parity. Staging has the current artifact and is **ALIGNED**. Ask for the relevant dated provisioning/build record; avoid a blanket collection of production configuration values.

### IAM: reduced topology and development-only components

The runtime has a documented intentional development difference. The test value equals production, but its record is from August 1: **UNKNOWN**, not aligned. Staging has a current supported reason that the provisioner does not exist in the fictional topology: **NOT APPLICABLE**, not missing.

A mock endpoint exists only in development; the production reference is supported as non-applicable. Development is **NOT COMPARABLE** against that reference. Ask whether a contract test or a different integration reference would establish the intended behavior. Do not propose deploying the mock to production to create superficial symmetry.

## Follow-up and proportionate improvement register

The effort ranges below are fictional initial investigation assumptions, not prices, commitments or measured labor. Dependencies can overlap; consolidate shared requests before estimating a work package.

| Observation | Specific next evidence/action | Proposed accountable role | Initial effort assumption | Dependency and success evidence |
|---|---|---|---|---|
| ESS unexplained development database difference | Establish whether the difference is intentional and locate a paired current snapshot and purpose record. | Service maintainer with test lead | 1–4 hours | Access to nonsecret version metadata; both values and testing limitation are recorded. |
| ESS overdue staging explanation | Review both expected values and the compatibility purpose; retain or revise the rationale with a new review basis. | Test-environment maintainer | 1–3 hours | Functional owner confirms the test purpose; decision is traceable and does not erase old history. |
| ESS production reference missing | Obtain one current worker-count observation and link all affected rows to it. | Operations evidence owner | 1–2 hours shared | One scoped artifact resolves the three comparisons; no invented observation. |
| RIS boolean/integer difference | Inspect the configuration contract and a representative behavior test using fictional settings. | Application maintainer | 1–4 hours | Record whether equivalence is actually demonstrated; preserve representations in source evidence. |
| RIS provisioning record unavailable | Locate the versioned image/build reference or preserve the missing-record finding. | Environment maintainer | 1–3 hours shared | Another practitioner can follow the record to the relevant nonsecret build input. |
| IAM stale test snapshot | Obtain a purpose-appropriate current observation; keep the older record as history. | Service operations role | 1–2 hours | Comparison cites the new snapshot with its actual represented date. |
| IAM production baseline not applicable | Select a contract/behavior-based alternative and state what it establishes. | Test lead and service maintainer | 2–6 hours | One example shows the development-only component's intended behavior without inventing a production counterpart. |

## Review and acceptance checklist

A usable packet names the service and environment purposes; preserves exact values, types, dates, source locators and rationale history; distinguishes intentional differences, unanswered questions and expired explanations; and connects each proposed action to a specific testing or operational consequence hypothesis. Every conclusion is reconstructible from supplied evidence or is explicitly unknown.

The answer sheet contains **21 comparisons: 4 aligned, 2 intentional differences, 2 unexplained differences, 1 explanation review due, 9 unknown, 2 not applicable and 1 not comparable**. Only nine comparisons have current comparable observations. These are known fictional exercise outcomes, not a claim about organizational maturity or the proportion of real environments with problems.

Record disagreements here rather than replacing the source account:

| Row / source | Reviewer A interpretation and support | Reviewer B interpretation and support | Evidence or question that resolves the difference | Disposition / still unresolved |
|---|---|---|---|---|
| [row and exact locator] | [claim + support] | [claim + support] | [focused next step] | [record decision or unknown] |

## Handoff boundaries

Hand off this method, the completed matrix, referenced nonsecret evidence locations, the grouped follow-up register and any unresolved interpretations. Real evidence must remain inside its approved storage boundary. The public synthetic packet must never receive private University records.

A downstream report may describe a supported observation or a focused evidence gap; it must not convert a row's provisional impact into a proven cause. A recommendation may serve several affected rows without being counted several times. This packet does not replace the workbench, interview sampling plan, deployment-recovery assessor or infrastructure reconstruction instrument; it supplies the environment-comparison evidence that those workflows can cite.
