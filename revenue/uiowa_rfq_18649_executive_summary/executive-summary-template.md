# {{Engagement name}} — leadership executive summary

**DRAFT — editable template.** Braced text is a placeholder, not a finding or
decision. The seeded IDs below belong to the published fictional rehearsal.
For another engagement, use that engagement's existing finding, recommendation
and evidence IDs and retain them across its summaries and planning inputs.

**Version:** {{document version}}  
**Scope and period:** {{services, workflows and period actually covered}}  
**Evidence bundle:** {{source bundle name/version and link}}  
**Planning source:** {{plan_id, version, source name and locator}}  
**Decision status:** DRAFT / NOT ACCEPTED

## Leadership view

### F-001 — {{supported strength}}

**S-001.** {{State the supported strength narrowly, without extending the finding
beyond the covered behavior.}}

**Evidence:** E-001; E-002; E-003.  
**Supplied confidence:** {{label, or NOT SUPPLIED}}  
**Limitation:** {{what the evidence does not establish}}

### F-002 — {{consequential gap}}

**S-002.** {{State the evidenced gap and its decision relevance. Distinguish
missing retained evidence from proof that an activity did not occur.}}

**Evidence:** E-004; E-005; E-006.  
**Linked recommendation:** [R-001](#r-001--proposed-decision).  
**Supplied confidence:** {{label, or NOT SUPPLIED}}  
**Limitation:** {{uncertainty and unassessed scope}}

### F-003 — {{mixed finding or coverage boundary}}

**S-003.** {{Separate the supported portion from the unassessed portion; do not
extend a representative result to the whole population.}}

**Evidence:** E-007; E-008.  
**Linked recommendation:** [R-002](#r-002--proposed-decision).  
**Supplied confidence:** {{label, or NOT SUPPLIED}}  
**Limitation:** {{coverage boundary}}

## Decisions and practical sequencing

### R-001 — proposed decision

**S-004.** {{Proposed action supported by F-002.}}  
**Expected outcome:** {{desired effect; not a measured result}}  
**Finding and evidence chain:** F-002 → E-004; E-005; E-006.  
**Planning record:** P-001, in the identified planning source.

| Planning field | Supplied value |
|---|---|
| Accountable owner | NOT SUPPLIED |
| Priority | NOT SUPPLIED |
| Sequence | NOT SUPPLIED |
| Timing and dependencies | NOT SUPPLIED |
| Resource assumptions | NOT SUPPLIED |
| Source of planning values | NOT SUPPLIED |

### R-002 — proposed decision

**S-005.** {{Proposed action supported by F-003.}}  
**Expected outcome:** {{desired effect; not a measured result}}  
**Finding and evidence chain:** F-003 → E-007; E-008.  
**Planning record:** P-002, in the identified planning source.

| Planning field | Supplied value |
|---|---|
| Accountable owner | NOT SUPPLIED |
| Priority | NOT SUPPLIED |
| Sequence | NOT SUPPLIED |
| Timing and dependencies | NOT SUPPLIED |
| Resource assumptions | NOT SUPPLIED |
| Source of planning values | NOT SUPPLIED |

## Outcome measures and resources

Fill a target only from an explicit planning decision. Fill an observed value only
from a supplied measurement, with its period and evidence reference. An absent
value remains `NOT SUPPLIED`; quoted zero in the planning JSON remains zero.

| Stable measure ID | Recommendation / plan | Measure and unit | Baseline | Proposed target | Observed value | Observation period and evidence |
|---|---|---|---|---|---|---|
| M-RIS-001 | R-001 / P-001 | {{measure and unit}} | NOT SUPPLIED | NOT SUPPLIED | NOT SUPPLIED | NOT SUPPLIED |
| M-IAM-001 | R-002 / P-002 | {{measure and unit}} | NOT SUPPLIED | NOT SUPPLIED | NOT SUPPLIED | NOT SUPPLIED |

**Supplied implementation effort:** {{retain the source labels; do not convert
them to hours without a supplied estimate}}  
**Staffing, hours and budget:** NOT SUPPLIED  
**Cash savings:** NOT ESTIMATED  
**Unresolved decisions:** {{owners, sequencing, dependencies, resources or
measurement inputs that are still missing}}

## Trace and editing guide

| Statement | Finding | Recommendation / plan | Evidence IDs |
|---|---|---|---|
| S-001 | F-001 | — | E-001; E-002; E-003 |
| S-002; S-004 | F-002 | R-001 / P-001 | E-004; E-005; E-006 |
| S-003; S-005 | F-003 | R-002 / P-002 | E-007; E-008 |

Seeded source registers: [findings](../uiowa_rfq_18649_traceability_rehearsal/findings.csv),
[recommendations](../uiowa_rfq_18649_traceability_rehearsal/recommendations.csv),
[evidence and locators](../uiowa_rfq_18649_traceability_rehearsal/evidence.csv), and
[statement trace map](../uiowa_rfq_18649_traceability_rehearsal/trace-map.csv).
Use the [editable planning JSON](planning-template.json) for P-001/P-002; add the
stable measure IDs above when supplying outcome-measure records. Its source
name/locator identifies planning assumptions separately from finding evidence.

Update the source bundle and trace map when changing an authoritative statement;
update the planning input when changing a proposed decision. This hand-edited
document remains a draft and is not automatically revalidated. The
[worked executive summary](executive-summary-example.md) shows a complete
fictional use of these same IDs. The [renderer guide](README.md) provides the
detailed portable briefing and structured JSON workflow.
