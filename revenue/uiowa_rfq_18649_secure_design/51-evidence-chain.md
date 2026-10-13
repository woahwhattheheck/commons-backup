# Sample evidence chain — secure design

**SYNTHETIC.** A worked chain from a fictional data flow to the requirement that governs it, the design decision that should have applied it, and the artifacts that do or do not establish that. Not a finding.

Reference frame: NIST SP 800-218, Secure Software Development Framework (SSDF) — https://csrc.nist.gov/Projects/ssdf. 
SSDF practice identifiers organize this instrument only. No output here is a conformance statement, certification, attestation, compliance verdict or assessment against the framework. The descriptions above are paraphrases written for this worksheet, not quotations; the authoritative wording is at https://csrc.nist.gov/Projects/ssdf.

## `DD-SYN-01` ← `SEC-REQ-SYN-01` (v3) — `TRACED_STALE`

**Data flow** `FLOW-SYN-01` — Student record extract from the student system to a reporting store  
student system (fictional) → reporting store (fictional) · data: identifiable records · **crosses a trust boundary**

**Requirement** — Identifiable records leaving the student system must be reduced to the fields the receiving purpose needs, and the reduction must be stated in the design.

Change history:

- v1 (fictional): required encryption in transit only.
- v2 (fictional): added the field-reduction obligation.
- v3 (fictional): required the reduction to be stated in the design record, not only performed. This is the change that makes a v2 trace stale rather than merely old.

**Design decision** — Reporting extract selects a fixed column list rather than the full record

*Decided:* 2026-04-14

**State: `TRACED_STALE`** — A design artifact cites this requirement, but at a superseded version. The link still resolves, and it resolves to text that has since changed. Neither traced nor untraced.

*Stale trace:*

- `EV-SD-SYN-03` (design_decision_record) cites v2 — Design record states the extract was reduced to a fixed column list, citing the requirement at v2  
  `synthetic-design-record-DD-SYN-01#security`

*Documented intent:*

- `EV-SD-SYN-02` (design_template) — The design record template, in use for this decision, contains a 'security requirements considered' section  
  `synthetic-design-template-v2.docx`

*Names the requirement but no decision:*

- `EV-SD-SYN-09` (requirement_change_record) cites v3 — Change record for SEC-REQ-SYN-01 v2 to v3, adding the obligation to state the reduction in the design  
  `synthetic-requirement-change-2026-06-01`

**Next step:** The trace points at SEC-REQ-SYN-01 v2, superseded by v3. Ask what changed between those versions and whether DD-SYN-01 was revisited. This is the case that looks fine in a traceability matrix.

## `DD-SYN-01` ← `SEC-REQ-SYN-03` (v2) — `OBSERVED_PRACTICE`

**Data flow** `FLOW-SYN-01` — Student record extract from the student system to a reporting store  
student system (fictional) → reporting store (fictional) · data: identifiable records · **crosses a trust boundary**

**Requirement** — A design that moves identifiable records across a trust boundary must have a data-flow model and a recorded design review.

Change history:

- v1 (fictional): required a data-flow model.
- v2 (fictional): added the recorded design review.

**Design decision** — Reporting extract selects a fixed column list rather than the full record

*Decided:* 2026-04-14

**State: `OBSERVED_PRACTICE`** — An artifact exists for this requirement at its current version. What it shows is a matter for the reviewer; that it exists is observed.

*Observed practice:*

- `EV-SD-SYN-04` (data_flow_diagram) cites v2 — Data-flow model covering the student system to reporting store path  
  `synthetic-dfd-FLOW-SYN-01-v3.png`
- `EV-SD-SYN-05` (design_review_record) cites v2 — Design review recorded, reviewer named, requirement confirmed considered  
  `synthetic-design-review-2026-04-16`

*Documented intent:*

- `EV-SD-SYN-01` (written_standard) — A published secure-design standard requires a data-flow model for any design crossing a trust boundary  
  `synthetic-secure-design-standard-v4.pdf`
- `EV-SD-SYN-02` (design_template) — The design record template, in use for this decision, contains a 'security requirements considered' section  
  `synthetic-design-template-v2.docx`

## `DD-SYN-02` ← `SEC-REQ-SYN-02` (v1) — `OBSERVED_PRACTICE`

**Data flow** `FLOW-SYN-02` — Build artifacts pushed from the pipeline to the deployment target  
build pipeline (fictional) → deployment target (fictional) · data: software artifacts · **crosses a trust boundary**

**Requirement** — Artifacts promoted to a deployment target must be attributable to the build that produced them.

**Design decision** — Promotion copies the artifact and records the originating build identifier

*Decided:* 2026-05-02

**State: `OBSERVED_PRACTICE`** — An artifact exists for this requirement at its current version. What it shows is a matter for the reviewer; that it exists is observed.

*Observed practice:*

- `EV-SD-SYN-06` (design_decision_record) cites v1 — Design record states the originating build identifier is carried with the artifact  
  `synthetic-design-record-DD-SYN-02#security`

## `DD-SYN-03` ← `SEC-REQ-SYN-03` (v2) — `DOCUMENTED_INTENT`

**Data flow** `FLOW-SYN-03` — Diagnostic export pulled by a support engineer to a local workstation  
application support console (fictional) → engineer workstation (fictional) · data: identifiable records · **crosses a trust boundary**

**Requirement** — A design that moves identifiable records across a trust boundary must have a data-flow model and a recorded design review.

Change history:

- v1 (fictional): required a data-flow model.
- v2 (fictional): added the recorded design review.

**Design decision** — Support diagnostic export runs against a filtered view

*Decided:* 2026-06-20

**State: `DOCUMENTED_INTENT`** — A standard, template or policy says this should happen. That is evidence about an intention. It says nothing about whether this design decision did it.

*Documented intent:*

- `EV-SD-SYN-01` (written_standard) — A published secure-design standard requires a data-flow model for any design crossing a trust boundary  
  `synthetic-secure-design-standard-v4.pdf`

*Names the requirement but no decision:*

- `EV-SD-SYN-07` (threat_model_record) cites v2 — A threat model covering the diagnostic export exists but names no design decision  
  `synthetic-threat-model-support-export`

**Next step:** A standard requires this; nothing shows DD-SYN-03 applied it. Ask for the design record or review note for this decision specifically. A template that says a section should exist is not that section.

## `DD-SYN-04` ← `SEC-REQ-SYN-04` (v1) — `DOCUMENTED_INTENT`

**Data flow** `FLOW-SYN-04` — Scheduled job reading configuration from the shared configuration service  
shared configuration service (fictional) → scheduled job (fictional) · data: configuration

**Requirement** — Scheduled jobs must read configuration through the shared service rather than embedding values.

**Design decision** — Scheduled job reads its connection settings at start-up

*Decided:* 2026-07-08

**State: `DOCUMENTED_INTENT`** — A standard, template or policy says this should happen. That is evidence about an intention. It says nothing about whether this design decision did it.

*Documented intent:*

- `EV-SD-SYN-08` (policy_statement) — A published policy requires scheduled jobs to use the shared configuration service  
  `synthetic-configuration-policy-v1.pdf`

**Next step:** A standard requires this; nothing shows DD-SYN-04 applied it. Ask for the design record or review note for this decision specifically. A template that says a section should exist is not that section.

## `DD-SYN-05` ← `SEC-REQ-SYN-01` (v3) — `UNKNOWN`

**Data flow** `FLOW-SYN-01` — Student record extract from the student system to a reporting store  
student system (fictional) → reporting store (fictional) · data: identifiable records · **crosses a trust boundary**

**Requirement** — Identifiable records leaving the student system must be reduced to the fields the receiving purpose needs, and the reduction must be stated in the design.

Change history:

- v1 (fictional): required encryption in transit only.
- v2 (fictional): added the field-reduction obligation.
- v3 (fictional): required the reduction to be stated in the design record, not only performed. This is the change that makes a v2 trace stale rather than merely old.

**Design decision** — Reporting store retains the extract for the full academic year

*Decided:* 2026-04-14

**State: `UNKNOWN`** — Nothing has been supplied for this requirement and this design decision. An open question -- not a gap, and not a pass.

*Names the requirement but no decision:*

- `EV-SD-SYN-09` (requirement_change_record) cites v3 — Change record for SEC-REQ-SYN-01 v2 to v3, adding the obligation to state the reduction in the design  
  `synthetic-requirement-change-2026-06-01`

**Next step:** Ask for any artifact that shows DD-SYN-05 considered SEC-REQ-SYN-01: a design decision record, a data-flow or threat model covering the flow, or a design review note. If none exists, that is the finding -- do not infer one from the standard.

---

No individual is assessed anywhere above. The subject is always an artifact's existence and which requirement version it cites.
