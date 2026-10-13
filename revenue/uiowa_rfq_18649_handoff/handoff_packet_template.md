# Development-to-operations handoff packet

> Worksheet status: proposed assessment template. Completing this worksheet does not constitute release approval.

## 1. Change identity

- Change ID:
- Change type: planned_release | urgent_maintenance
- Service:
- Group: ESS | RIS | IAM
- Summary:
- Requested/user-facing behavior:
- Implementation owner role:
- Support owner role:
- Release trigger/window:
- If urgent maintenance, urgency reason:
- Synthetic/example packet: yes | no

## 2. User-facing behavior

- Before:
- After:
- Affected user/persona groups:
- Communication/support message:

## 3. Known limitations

For each limitation record:
- limitation ID;
- description;
- affected scope;
- owner role;
- mitigation/workaround, if any;
- follow-up trigger.

Use an explicit `none_known` entry when no limitations are known; do not leave the section blank.

## 4. Requirements and acceptance traceability

For each requirement:
- requirement ID;
- statement;
- acceptance criteria;
- acceptance evidence IDs;
- support/operational readiness IDs.

A requirement is incomplete for handoff review if it has no acceptance evidence or no support/operational readiness linkage.

## 5. Acceptance evidence

For each evidence item:
- evidence ID;
- type (test, user acceptance, review, observation, other);
- exact locator;
- observed result;
- notes/limitations.

Evidence is a reference to an artifact or observation, not a claim that the entire release is acceptable.

## 6. Support readiness

For each support item:
- support item ID;
- information/task;
- owner role;
- state: complete | pending | deferred_with_owner;
- locator or follow-up trigger.

Examples: support decision tree, service desk knowledge article, known-error note, escalation path, user communication.

## 7. Documentation updates

For each document:
- document name;
- owner role;
- state: updated | reviewed_no_change | pending | deferred_with_owner;
- locator or follow-up trigger.

For urgent maintenance, a deferred update is visible and owned; urgency does not erase the documentation debt.

## 8. Operational needs

For each operational item:
- operational item ID;
- kind: monitoring | dependency | access | data | capacity | runbook | other;
- need;
- owner role;
- state: complete | pending | deferred_with_owner;
- verification/locator or follow-up trigger.

## 9. Rollback and recovery

- rollback trigger:
- rollback method:
- data recovery notes:
- owner role:

This section records the handoff information. It does not itself validate a rollback design.

## 10. Open items / unresolved information

For each item:
- open-item ID;
- severity: blocking | non_blocking;
- question/missing information;
- owner role;
- resolution trigger.

Do not convert unresolved evidence into an inferred answer.

## 11. Reviewer prompts

- Can each requirement be followed to acceptance evidence?
- Can each requirement be followed to support or operational preparation?
- Are known limitations visible to support?
- Are operational dependencies/monitoring needs owned?
- Can the support owner identify escalation and recovery contacts/roles?
- Does urgent work retain explicit follow-up for anything deferred?
- Which statements are artifacts/observations, and which are still assertions?
