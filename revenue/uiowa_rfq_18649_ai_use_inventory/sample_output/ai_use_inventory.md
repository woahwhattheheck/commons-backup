# AI-use inventory -- synthetic baseline (UIOWA-071)

**All records below are fictional.** They were written to rehearse the
discovery instrument. No University input has been collected; every
University figure in this document is therefore absent, not zero.

Source collection: `uiowa-synthetic-ai-use-20260919-01` -- 10 records.

## How the records classified

| Classification | Records | Reading |
| --- | ---: | --- |
| ACTIVE_USE | 2 | running work, with a concrete example behind it |
| INFORMAL_EXPERIMENT | 4 | real use, but not yet an operated workflow |
| PLANNED_USE | 2 | intended; nothing observed yet |
| UNSUPPORTED_CLAIM | 1 | use asserted, nothing demonstrates it -- left unfilled on purpose |
| UNKNOWN | 1 | not enough captured to classify |

These five are reported separately and are never combined into an
adoption percentage. `UNSUPPORTED_CLAIM` in particular is a count of
claims that did not survive a request for an example; folding it into
active use is the exact error this instrument exists to prevent.

## Coverage by group and function

| Group | Function | Entries | State |
| --- | --- | ---: | --- |
| ESS | development | 1 | ACTIVE_USE_PRESENT |
| ESS | documentation | 1 | CLAIMED_UNSUPPORTED |
| ESS | testing | 1 | INFORMAL_ONLY |
| ESS | support | 0 | NO_ENTRY_CAPTURED |
| ESS | analysis | 1 | INFORMAL_ONLY |
| RIS | development | 1 | PLANNED_ONLY |
| RIS | documentation | 0 | NO_ENTRY_CAPTURED |
| RIS | testing | 0 | NO_ENTRY_CAPTURED |
| RIS | support | 1 | PLANNED_ONLY |
| RIS | analysis | 1 | INFORMAL_ONLY |
| IAM | development | 0 | NO_ENTRY_CAPTURED |
| IAM | documentation | 1 | UNKNOWN |
| IAM | testing | 0 | NO_ENTRY_CAPTURED |
| IAM | support | 1 | ACTIVE_USE_PRESENT |
| IAM | analysis | 1 | INFORMAL_ONLY |

`NO_ENTRY_CAPTURED` means nobody in that group was asked about that
function. It is not a finding of no AI use.

## Entries

### AIU-SYN-001 -- ESS / development

- **Task:** In-editor code completion and short refactor suggestions while writing service code
- **Declared:** ACTIVE -> **classified:** ACTIVE_USE
- **Frequency:** DAILY | **Users:** application developer (9)
- **Inputs:** the open source file; the surrounding repository context
- **Outputs:** suggested code accepted into a branch before review
- **Integrations:** the team's IDE; the existing pull-request review flow (REPORTED)
- **Benefits:** 1 with an example, 0 unsupported
- **Known limitations:** suggestions are wrong often enough that review was never relaxed; not used on the payment-adjacent module by team decision
- **Evidence locators:** synthetic://uiowa-rfq18649/AIU-SYN-001/pr-1184

### AIU-SYN-002 -- ESS / testing

- **Task:** Generating first-draft unit test scaffolds for legacy modules that have none
- **Declared:** ACTIVE -> **classified:** INFORMAL_EXPERIMENT  *(demoted)*
- **Frequency:** AD_HOC | **Users:** application developer (3)
- **Inputs:** the legacy module source
- **Outputs:** a draft test file that a developer then rewrites
- **Integrations:** the team's IDE (REPORTED)
- **Benefits:** 1 with an example, 0 unsupported
- **Known limitations:** generated assertions are frequently trivial and get deleted
- **Evidence locators:** synthetic://uiowa-rfq18649/AIU-SYN-002/branch-legacy-tests
- **Why:** frequency is AD_HOC, not a recurring cadence; recorded as an informal experiment rather than active use

### AIU-SYN-003 -- ESS / documentation

- **Task:** Writing release notes from commit history
- **Declared:** ACTIVE -> **classified:** UNSUPPORTED_CLAIM  *(demoted)*
- **Frequency:** MONTHLY | **Users:** application developer (UNKNOWN)
- **Inputs:** commit messages
- **Outputs:** UNKNOWN
- **Integrations:** - (UNKNOWN)
- **Benefits:** 0 with an example, 1 unsupported
- **Known limitations:** NONE CAPTURED
- **Evidence locators:** NONE
- **Why:** use asserted (ACTIVE) with no evidence locator, no benefit example and no named output
- **Preparation work:**
    - `NO_CONCRETE_EXAMPLE` -- Ask for one specific instance from the last 30 days, with the artifact or ticket it produced.
    - `UNSUPPORTED_BENEFIT` -- Ask what the work looked like before, what it looks like now, and where that comparison can be seen.
    - `UNKNOWN_INTEGRATION` -- Ask whether this runs inside an existing system or is opened separately, and name the system.
    - `NO_LIMITATIONS_CAPTURED` -- Ask for the most recent case where the output was wrong or unusable and what happened next.
    - `UNKNOWN_USER_COUNT` -- Ask which roles use this and roughly how many people hold that role; team-level only.
    - `NO_EVIDENCE_LOCATOR` -- Ask where the output is stored so a locator can be recorded.

### AIU-SYN-004 -- RIS / analysis

- **Task:** Summarising free-text responses from an internal service survey
- **Declared:** INFORMAL -> **classified:** INFORMAL_EXPERIMENT
- **Frequency:** WEEKLY | **Users:** research support analyst (2)
- **Inputs:** exported survey free-text column
- **Outputs:** a themes memo circulated inside the team
- **Integrations:** - (NONE_REPORTED)
- **Benefits:** 1 with an example, 0 unsupported
- **Known limitations:** summaries flatten disagreement; the team re-reads outliers by hand
- **Evidence locators:** synthetic://uiowa-rfq18649/AIU-SYN-004/themes-memo-2026-08

### AIU-SYN-005 -- RIS / support

- **Task:** Proposed first-line triage of service-desk tickets
- **Declared:** PLANNED -> **classified:** PLANNED_USE
- **Frequency:** NOT_YET | **Users:** service desk analyst (6)
- **Inputs:** incoming ticket text
- **Outputs:** UNKNOWN
- **Integrations:** - (NONE_REPORTED)
- **Benefits:** 0 with an example, 0 unsupported
- **Known limitations:** no decision yet on how a misrouted ticket would be caught
- **Evidence locators:** NONE
- **Preparation work:**
    - `NO_EVIDENCE_LOCATOR` -- Ask where the output is stored so a locator can be recorded.

### AIU-SYN-006 -- RIS / development

- **Task:** Script generation for one-off data extracts
- **Declared:** PLANNED -> **classified:** PLANNED_USE
- **Frequency:** AD_HOC | **Users:** research support analyst (2)
- **Inputs:** a description of the extract needed
- **Outputs:** a Python script used for the August extract
- **Integrations:** - (UNKNOWN)
- **Benefits:** 1 with an example, 0 unsupported
- **Known limitations:** NONE CAPTURED
- **Evidence locators:** synthetic://uiowa-rfq18649/AIU-SYN-006/extract-2026-08
- **Why:** declared PLANNED but the record carries a concrete example; both readings preserved for a human to reconcile; benefits reported as observed for a use declared not-yet-started; these are projections until the use is running
- **Preparation work:**
    - `UNKNOWN_INTEGRATION` -- Ask whether this runs inside an existing system or is opened separately, and name the system.
    - `NO_LIMITATIONS_CAPTURED` -- Ask for the most recent case where the output was wrong or unusable and what happened next.
    - `STATUS_EVIDENCE_MISMATCH` -- Reconcile the declared status against the evidence with the team before it enters a finding.

### AIU-SYN-007 -- IAM / support

- **Task:** Drafting replies to routine access-request tickets for an analyst to edit and send
- **Declared:** ACTIVE -> **classified:** ACTIVE_USE
- **Frequency:** DAILY | **Users:** identity services analyst (4)
- **Inputs:** the ticket text; the standard response templates
- **Outputs:** a draft reply placed in the ticket for human edit
- **Integrations:** the ticketing system (REPORTED)
- **Benefits:** 1 with an example, 0 unsupported
- **Known limitations:** drafts are never sent unedited; not used for anything involving an exception to policy
- **Evidence locators:** synthetic://uiowa-rfq18649/AIU-SYN-007/ticket-sample-week-36

### AIU-SYN-008 -- IAM / analysis

- **Task:** Grouping quarterly access-review exceptions so a human reviews them in batches
- **Declared:** ACTIVE -> **classified:** INFORMAL_EXPERIMENT  *(demoted)*
- **Frequency:** MONTHLY | **Users:** identity services analyst (2)
- **Inputs:** the exported access-review exception list
- **Outputs:** a grouped worksheet used in the Q2 review
- **Integrations:** - (NONE_REPORTED)
- **Benefits:** 1 with an example, 0 unsupported
- **Known limitations:** the grouping is re-checked by hand before any access is changed
- **Evidence locators:** synthetic://uiowa-rfq18649/AIU-SYN-008/q2-review-worksheet
- **Why:** explicitly not integrated into a workflow; recorded as an informal experiment rather than active use

### AIU-SYN-009 -- IAM / documentation

- **Task:** Something involving drafting procedure text; the respondent was not sure who does it
- **Declared:** UNKNOWN -> **classified:** UNKNOWN
- **Frequency:** UNKNOWN | **Users:** UNKNOWN (UNKNOWN)
- **Inputs:** UNKNOWN
- **Outputs:** UNKNOWN
- **Integrations:** - (UNKNOWN)
- **Benefits:** 0 with an example, 0 unsupported
- **Known limitations:** NONE CAPTURED
- **Evidence locators:** NONE
- **Why:** declared_status was not captured; cannot separate active from planned use
- **Preparation work:**
    - `UNKNOWN_FREQUENCY` -- Ask how many times this was used in the last full week; record UNKNOWN if unsure rather than estimating.
    - `UNKNOWN_INTEGRATION` -- Ask whether this runs inside an existing system or is opened separately, and name the system.
    - `NO_LIMITATIONS_CAPTURED` -- Ask for the most recent case where the output was wrong or unusable and what happened next.
    - `UNKNOWN_USER_COUNT` -- Ask which roles use this and roughly how many people hold that role; team-level only.
    - `NO_EVIDENCE_LOCATOR` -- Ask where the output is stored so a locator can be recorded.

### AIU-SYN-010 -- ESS / analysis

- **Task:** Reading long vendor release notes and pulling out changes that affect the team
- **Declared:** INFORMAL -> **classified:** INFORMAL_EXPERIMENT
- **Frequency:** UNKNOWN | **Users:** application developer (UNKNOWN)
- **Inputs:** vendor release note PDFs
- **Outputs:** a short note pasted into the team channel
- **Integrations:** - (UNKNOWN)
- **Benefits:** 0 with an example, 1 unsupported
- **Known limitations:** nobody checks whether anything was missed
- **Evidence locators:** synthetic://uiowa-rfq18649/AIU-SYN-010/channel-note-2026-09
- **Preparation work:**
    - `UNSUPPORTED_BENEFIT` -- Ask what the work looked like before, what it looks like now, and where that comparison can be seen.
    - `UNKNOWN_FREQUENCY` -- Ask how many times this was used in the last full week; record UNKNOWN if unsure rather than estimating.
    - `UNKNOWN_INTEGRATION` -- Ask whether this runs inside an existing system or is opened separately, and name the system.
    - `UNKNOWN_USER_COUNT` -- Ask which roles use this and roughly how many people hold that role; team-level only.

## Still UNKNOWN (University inputs not collected)

- which units actually use AI tooling today, and under what approval
- whether any use touches student or restricted data, and under which access semantics
- existing license, contract or procurement coverage for any tool named
- whether informal experiments are known to the unit's leadership
- the real headcount behind any role named in an entry
