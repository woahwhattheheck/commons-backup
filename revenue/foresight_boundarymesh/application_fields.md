# Application field readiness map

Status: **HOLD_OWNER_INPUTS / FORM_SCHEMA_PARTIAL**. The public RFP and Airtable form URL are verified. Airtable's current field labels are client-rendered and were not exposed by the available text crawler, so this file deliberately does **not** invent exact form questions. Before submission, inspect the live form and map each field 1:1 here.

## Sponsor-confirmed inputs from the public RFP

| Input | Current draft state |
|---|---|
| RFP | AI for Science & Safety Nodes |
| Track | II. Coordination and accountability |
| Primary focus | Supercollaboration and decentralized alignment |
| Project title | BoundaryMesh: Open Boundary-Respecting Coordination and Verification for Many-Agent Systems |
| Deadline | 2026-10-31 23:59 PDT |
| Requested funding | Proposed $99,000; OWNER_CONFIRM before submission |
| Duration | Proposed 12 months; OWNER_CONFIRM |
| Open-source commitment | Yes for all grant-funded code, data, protocol specs, benchmark outputs, and reports |
| Applicant type | OWNER_CONFIRM: individual, team, or organization |
| Node participation | OWNER_CONFIRM; sponsor strongly prioritizes active in-person contribution |
| Lightcone Commons sharing | OWNER_CONFIRM if the live form offers the opt-in described in the RFP |

## Owner-confirm fields that must not be inferred

- Legal/applicant name and whether the application is individual or organizational.
- If organizational: exact entity type, jurisdiction, tax status, authorized submitter, and the truthful reason grant funding is needed.
- Primary applicant biography/CV facts and any collaborators actually committed to the project.
- Willingness and concrete availability for San Francisco or Berlin Node participation/sprints.
- Whether travel expenses are needed or separately sponsor-covered.
- Final requested amount, compensation basis, overhead treatment, and tax/accounting route.
- Foresight connections, due-diligence disclosures, tax/organizational documents, and any other sponsor-requested declarations.
- Public/private project-listing preference and Lightcone Commons sharing choice.
- Any compute request: model providers/hardware, privacy needs, expected units, and whether sponsor Node compute can substitute for cash budget.

## Draft answer modules ready for form mapping

1. **Problem / focus fit** — use `proposal.md` sections Problem and Fit.
2. **Project / technical approach** — use `proposal.md` Approach + `project_spec.json`.
3. **Why now / x-risk relevance** — use `proposal.md` Impact hypothesis; present it as a hypothesis to test, not a proven x-risk reduction claim.
4. **Milestones / timeline** — use `proposal.md` Milestones.
5. **Evaluation** — use `evaluation_plan.md` and the predeclared negative-result rule.
6. **Capability to execute** — use only the public, merged engineering evidence listed in `proposal.md`; do not convert internal engineering work into a client or academic credential.
7. **Open-source plan** — all grant-funded work public; existing unrelated/background systems remain outside funded scope and are not grant-charged.
8. **Budget** — use `budget.json` only after OWNER_CONFIRM.
9. **Node/community participation** — do not promise attendance until OWNER_CONFIRM.

## Submission gate

Do not submit until the live Airtable labels are captured, every required field is mapped, owner-confirm fields are resolved, attachments/CV/budget requirements are satisfied, and `python validate_pack.py` plus `python -m unittest -v test_pack.py` pass on the final bytes.
