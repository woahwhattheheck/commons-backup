# Operational analyst handover — SYNTHETIC

Packet `SYN138-HANDOVER` version **2**. Prepared by ZZ-BOREAL-138Q / GPT-6 Astra Pro for UIOWA-138. One assistant simulates both analyst roles; no independent human continuation or University review is claimed.

## What is current, and why

The selected discovery artifact is `091-DISCOVERY-SNAPSHOT` at commit `bcf765be4d537a513bf1d7ac54a210b25b053d07`. Its canonical source is `revenue/uiowa_rfq_18649_synthetic_collection/facts.json`; the source ID is `UIOWA-091-SYNTHETIC-AIS-001`. This fixed, merged UIOWA-091 snapshot makes the exercise replayable. It is not a promise that future `main` has unchanged bytes. Use the [source register](SOURCE_REGISTER.md) to select the exact versions. Original collection author: ZZ-Sol; merged PR #16172.

## Scope and task boundary

Context: fictional ESS, RIS and IAM analogues, across software development, security, deployment/operations and AI readiness. The next task is **three bounded cross-group release/recovery findings**, not a whole-engagement final report. Real University conclusions, employee assessments, formal compliance auditing, vendor procurement and staffing/meeting commitments are outside this rehearsal.

## Transfer of responsibility

Fictional analyst A has organized discovery; fictional analyst B completes synthesis. The fictional prime methodology lead retains professional judgment. No named person is assigned, booked or assumed available. In a live engagement, replace role placeholders through the existing agreed coordination process. Scenario windows are not appointments.

## Scope decisions and rationale

**D-01: Consume 091 facts and manifest rather than scrape prose into new scores.** Retain source-defined strength/gap/unknown and their original scope.

**D-02: Write three bounded findings, not a team ranking.** The examples cover different tasks and cannot be collapsed into common maturity scores.

**D-03: Continue synthesis while explicit evidence requests remain open.** The draft can express its limitations without inventing an answer; later evidence may change the draft.

## Evidence locations and selected task

Consume `facts.json` and `evidence_manifest.json` directly. `coverage_matrix.csv` supplies the 12-cell inventory. The unchanged native `validate_collection.py` checks source presence, synthetic labels, fact references, scopes and counts. It does not prove narrative meaning, measure maturity or establish real-world truth.

| Draft | Original fact IDs | Evidence to read |
|---|---|---|
| ESS rule/fixture version mismatch | ESS-SW-001; ESS-SW-002 | Release examples: REL-ESS-042 and REQ-ESS-043 |
| RIS deployment ordering versus demonstrated batch recovery | RIS-OPS-001; RIS-OPS-002 | INT-RIS-01, batch runbook and INC-RIS-014 |
| IAM monitoring versus demonstrated stateful recovery | IAM-OPS-001; IAM-OPS-002 | INC-IAM-031, INC-IAM-032 and INT-IAM-01 |

Exact source lines, original states and completed prose are in [SYNTHESIS.md](SYNTHESIS.md). Keep the 47-minute observation attached to the fictional RIS batch incident; do not transfer it to another operation or group.

## Outstanding inputs

**ESS-SEC-002 / OPEN.** Does any in-scope fixture use production-derived data, and what evidence establishes handling? Request the fixture inventory, lineage record and applicable handling procedure. Proposed role: fictional test-data steward. Do not request real sensitive data for this public demonstration.

**ESS-AI-002 / OPEN.** Does AI participate in the release-decision workflow within the stated scope? Request a workflow inventory and concrete decision trace or justified scoped non-use statement. Proposed role: fictional release lead.

**IAM-AI-001 / OPEN.** What system evidence establishes whether AI participates in authorization or entitlement decisions? Request the decision-path inventory and design/operating evidence. Testimony alone does not prove a system-wide negative. Proposed role: fictional service owner.

Finding-specific requests also remain in SYNTHESIS.md: rules-v9 test/fixture evidence, the schema-promotion ordering trace, and demonstrated stateful restoration. A completed draft is not receipt of those inputs.

## Reviewer context retained

These comments are authored scenario prompts, not comments actually received from Clark, Iowa or an independent reviewer.

**RC-01 / SYN138-F-ESS / ADDRESSED_IN_DRAFT** — Do not call all tests stale from one rule-version mismatch. Response: scope narrowed to REQ-ESS-043; the metadata-versus-content question remains explicit.

**RC-02 / SYN138-F-RIS / ADDRESSED_IN_DRAFT** — Do not apply the 47-minute batch incident to deployment ordering or IAM migration. Response: distinct tasks and populations stated; the number remains attached to INC-RIS-014 only.

**RC-03 / SYN138-F-IAM / ADDRESSED_IN_DRAFT** — Missing restoration evidence is not proof that recovery will fail. Response: retain the evidence boundary and request specific restoration artifacts.

**RC-04 / SYN138-F-IAM / OPEN_INPUT** — Has the latest restoration evidence been supplied? Response: no new evidence was supplied in this rehearsal; the request remains open, not claimed resolved.

## Relative delivery calendar

Weeks are relative to an agreed hypothetical kickoff. No date, person's availability, billing condition or final acceptance is asserted.

| Milestone | Scenario window | Predecessor | Deliverable/state |
|---|---|---|---|
| KICKOFF | Week 1 | Agreed kickoff | Scope and evidence request list / SCENARIO_BASELINE |
| DISCOVERY | Weeks 1–3 | KICKOFF | Versioned evidence inventory and unresolved input log / SIMULATED_COMPLETE |
| HANDOVER | Week 3 | DISCOVERY | This packet and scope decisions / SIMULATED_COMPLETE |
| SYNTHESIS | Weeks 3–4 | HANDOVER | Three draft findings, retained states and follow-ups / EXERCISED_NOT_CLIENT_DELIVERED |
| DRAFT_REVIEW | Weeks 4–6 | SYNTHESIS | Consolidated comments and unresolved evidence list / PROPOSED |
| FINAL | Weeks 6–8 | DRAFT_REVIEW | Revised packet with explicit residual limitations / PROPOSED |

## Next deliverable and completion criterion

`SYN138-SYNTHESIS-v1` is the prepared draft for the fictional prime methodology lead. This continuation task is complete when three bounded findings cite exact source lines and fact IDs, every original UNKNOWN remains explicit, all four comments retain a response or open-input disposition, and next delivery dependencies remain readable.

The actual run produced that draft. Consolidated review follows synthesis; final delivery remains a proposed later phase. Real University assessment, client acceptance, payment entitlement and closure of evidence requests are **not** established.

## Source-version change procedure

Preserve this packet and prior outputs. Capture the new source revision, identify affected fact IDs/citations, and revise the finding and response deliberately. Do not silently substitute current main, resolve an open question or carry old review meaning onto changed evidence. The executable companion checks byte/line continuity; professional judgment still determines whether changed content changes the finding.
