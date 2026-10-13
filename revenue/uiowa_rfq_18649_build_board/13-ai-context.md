# UIOWA-013 — Iowa AI strategy and data-use context

**Purpose:** Public-source kickoff reference for the AI-readiness portion of University of Iowa RFQ 18649.  
**Source access date:** 2026-09-19.

> **Evidence boundary:** University-wide public guidance is context, not proof of practice. Nothing in this file establishes that ESS, RIS, IAM, or another AIS team uses a particular AI tool or workflow.

## 1. What is requirement, guidance, and strategy?

| Type | Official source | Assessment use |
|---|---|---|
| Formal policy | Institutional Data Policy (IT-19) | Establishes data classifications, access/secondary-use rules, and stewardship responsibilities |
| Security/data handling guidance | Data handling guidelines | States AI handling expectations by classification, including security review for non-public data |
| Current AI guidance | AI at Iowa — Guidance and Policies / Using AI Responsibly | Current responsible-use front door: approved tools, data awareness, output verification, role-specific guidance |
| Strategy | Guiding Principles + AI Action Plan | Establishes institutional direction, literacy, human accountability, training, pilots, and support priorities |
| Tool-specific service guidance | ITS AI tools and service pages | Establishes tool-specific supported data levels, current service constraints, and retention |
| Role guidance | Administration and Staff; Research and Scholarship; teaching pages | Gives role-specific examples, risk framing, and boundaries |

## 2. Institutional data rules relevant to AI

The **Institutional Data Policy (IT-19)** defines four classifications: Public, University-Internal, Restricted, and Critical. Unless otherwise classified, institutional data is University-Internal. Copying or moving data does not change its classification. Non-public data use remains limited by authorization and purpose.

Source: https://itsecurity.uiowa.edu/policies-standards-guidelines/institutional-data-policy  
Status: reviewed 2023-09-27.

The **Data handling guidelines** include an explicit Artificial Intelligence row:

- Critical — security review required
- Restricted — security review required
- University-Internal — security review required
- Public — OK

Source: https://itsecurity.uiowa.edu/awareness/data-types-and-regulations/data-handling-guidelines  
Status: last updated 2025-06-10.

**AIS implication:** before AI-assisted analysis, documentation, coding, or support work, determine what University data enters the workflow and which tool-specific approval applies.

## 3. Current responsible-use guidance

The current AI at Iowa hub says to:

1. use institutionally supported tools whenever possible;
2. understand University data classifications;
3. verify AI output and exercise human judgment; and
4. follow role-specific guidance.

It also states that implementations of new AI tools are subject to University security review.

Sources:
- https://ai.uiowa.edu/guidance-and-policies
- https://ai.uiowa.edu/using-ai-responsibly

The responsible-use page further says that AI services without a University contract or agreement should only be used with Public institutional data.

## 4. Tool-specific data permissions

The current ITS **AI tools** matrix is more specific than brand-level assumptions. It lists permitted data levels by supported service. For example, the University of Iowa ChatGPT Edu enterprise license is listed for Public and University-Internal data, with Restricted/Critical use requiring consultation with Research Services or ITS-ISPO.

Source: https://its.uiowa.edu/ai-tools

**Assessment rule:** approval should be evaluated as **tool/service + account/workspace + data classification + use case + review status**, not merely by the model or vendor name.

## 5. Strategy and action plan

The current **Guiding Principles** describe AI as a way to amplify human potential while retaining human judgment and accountability. Themes include collaboration, continuing AI literacy, responsibility, integrity, transparency, privacy, fairness, accessibility, and security.

Source: https://ai.uiowa.edu/guidance-and-policies/guiding-principles

The **AI Action Plan** includes recommendations directly relevant to readiness interviews:

- staff AI training (Actions 37–39);
- pilots, experimentation, and monitoring useful tools (Actions 40–42);
- dedicated support for training, consulting, and implementation (Action 43);
- continued updates to privacy, security, appropriate-use, and ethics guidance;
- measures such as support requests, participation, cost savings, and lead time.

Source: https://its.uiowa.edu/university-iowa-artificial-intelligence-action-plan

These are strategy/readiness themes, not evidence that a given AIS group has completed them.

## 6. Staff and software-development context

Current **AI for Administration and Staff** guidance includes IT/technical examples such as code snippets, technical documentation, and explanation of scripts or log output. It also reiterates approved-tool use, data handling, output review, and human responsibility.

Source: https://ai.uiowa.edu/ai-administration-and-staff

The current **Using AI Responsibly** page classifies AI code generation as Medium Risk, advises caution, says routine code blocks may be AI-assisted, says entire programs should not be written by AI, and requires thorough testing.

Source: https://ai.uiowa.edu/using-ai-responsibly

**AIS implication:** interviews should distinguish limited assistive use from broad AI-generated implementation and ask what normal review/test gates apply.

## 7. Research boundary

Current **AI for Research and Scholarship** guidance says researchers remain responsible for data protection, sponsor/contract limits, human-subject considerations, research integrity, disclosure/authorship expectations, and verification of AI output. It directs users to the current tool matrix for approved services and data levels.

Source: https://ai.uiowa.edu/ai-research-and-scholarship

**RIS implication:** do not assume that every RIS artifact is research data or that all research data has one classification. Ask about the actual data and sponsor/contract constraints for each use case.

## 8. Teaching and student boundary

Current University teaching guidance treats acceptable AI use as context-dependent and calls for clear instructor expectations at course and assignment level. It cautions against AI detectors because of false positives and calls attention to privacy, accessibility, and alternatives when AI is part of coursework.

Sources:
- https://teach.its.uiowa.edu/artificial-intelligence-tools-and-teaching
- https://teach.its.uiowa.edu/news/2025/08/teaching-ai-setting-expectations-your-syllabus

**ESS implication:** this becomes relevant only where a concrete ESS workflow touches instruction, assessment, student-facing AI, or student records. The public guidance is not evidence that any ESS application includes AI.

## 9. Staff enablement

The University currently advertises an AI support ecosystem including the AI Support Team, supported tools, AI Pathways, AI Explorer Grants, Lightning Talks, user groups, training, and consultation.

Sources:
- https://its.uiowa.edu/news/2026/06/starting-point-ai-tools-training-and-support
- https://its.uiowa.edu/ai

**Readiness question:** do AIS staff know the approved-tool matrix, data classification scheme, review path, and support/training resources?

## 10. Retention/lifecycle

The University announced a six-month chat-history retention policy for supported Microsoft Copilot services and ChatGPT Edu, effective 2026-08-03. Material needed beyond that period should be saved in an appropriate durable University location rather than relying on chat history.

Sources:
- https://its.uiowa.edu/news/2026/07/university-implement-six-month-retention-policy-ai-chat-history
- https://its.uiowa.edu/services/chatgpt-edu/how-use-chatgpt-edu

**AIS implication:** determine which AI-derived technical decisions or records must persist and where they are retained.

## 11. Guidance tension / supersession watch

No reviewed source explicitly declares the older ITS AI pages rescinded, so this document does **not** call them invalid. However, there is wording that should be reconciled:

| Topic | Observed tension | Assessment treatment |
|---|---|---|
| Non-public data | Some older/parallel research wording broadly warns against non-public data in AI, while the current tool matrix gives specific supported services permitted data levels and consultation conditions | Prefer the current tool-specific matrix plus review status for operational questions; ask the University to confirm unresolved conflicts |
| Governance front door | Older ITS AI Guidelines remain live while the 2026 ai.uiowa.edu site is the centralized current guidance hub | Use the 2026 hub for navigation; retain older pages for non-conflicting detail |
| Strategy | Older ITS strategy page remains live alongside the current AI at Iowa Guiding Principles | Treat both as strategy, never as proof of team adoption |
| Chat lifecycle | Older guidance lacks the newer common six-month supported-chat rule | Use the July/August 2026 retention sources for current lifecycle questions |

Related live pages:
- https://its.uiowa.edu/ai-guidelines-and-use-cases
- https://ai.uiowa.edu/guidance-and-policies
- https://its.uiowa.edu/ai-tools
- https://ai.uiowa.edu/ai-research-and-scholarship

## 12. Policy-to-discovery-question table

| Source / principle | AIS discovery question | Evidence to request |
|---|---|---|
| Institutional Data Policy | How are code, tickets, logs, prompts, test data, exports, and outputs classified before AI use? | Local classification examples and data-owner guidance |
| Data handling guidelines | Which AI-assisted use cases involving non-public data have completed required review? | Review/approval record and approved scope |
| Current AI tool matrix | What exact service/account/workspace is used for each AI workflow, and what data level is permitted? | Tool inventory and current approval matrix |
| Human accountability guidance | Where must a person review AI-generated code, documentation, analysis, or recommendations before acceptance? | Review checklist, PR/QA rules, approval records |
| Code-generation guidance | What types of code assistance are permitted and what test gates apply? | Coding standard and CI/test requirements |
| Guiding Principles | Which responsibility, privacy, accessibility, fairness, and security principles have concrete owners/controls? | Ownership/RACI and review evidence |
| AI Action Plan | What role-specific AI training and support paths exist for AIS staff? | Training records, support links, consultation examples |
| Research guidance | How are sponsor, contract, human-subject, and research-data constraints identified before AI use? | Decision process and representative examples |
| Teaching guidance | For any student-facing AI capability, who sets acceptable-use expectations and accessibility/privacy requirements? | Product requirements and policy handoff |
| Six-month chat retention | Which AI-derived records must persist longer, and where are they stored? | Records/decision documentation |
| Chatbot guidance | If a chatbot is operated or planned, who owns review, monitoring, data selection, and lifecycle maintenance? | Ownership, review and test plan |

## 13. High-value kickoff questions

1. What AI tools or embedded AI features are actually used by ESS, RIS, or IAM today?
2. What data enters each workflow and how is it classified?
3. What review/approval applies to that exact service and use case?
4. Are users in University enterprise workspaces or personal/public accounts?
5. What human review and testing applies to AI-assisted code or technical analysis?
6. Which records must be durable beyond AI chat retention?
7. Who has authority to approve AI-assisted decisions that affect access, research restrictions, student-facing behavior, or production change?
8. How are vendor-added AI features evaluated when they appear inside an already-used platform?
9. What staff training has been completed, and what escalation path is used when guidance is unclear?
10. What evidence can demonstrate the claimed controls rather than relying only on interview assertion?

## 14. Guardrails

- Do not infer team adoption from University AI strategy.
- Do not infer maturity from public central guidance.
- Do not treat a vendor/model name as a single security posture.
- Do not present synthetic/demo materials as University production findings.
- Do not assume a policy is implemented uniformly across units without evidence.
- Treat conflicting public guidance as a discovery item to reconcile with the responsible University owner.

## 15. Completion check

- [x] Current official Iowa AI strategy and data-use guidance captured.
- [x] Requirements, guidance, and strategy separated.
- [x] Teaching, research, staff, data, tool, and retention boundaries covered.
- [x] Guidance tension identified without declaring live pages invalid.
- [x] Policy-to-discovery questions included.
- [x] No public statement used as evidence of ESS/RIS/IAM adoption.
