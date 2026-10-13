# Change trace timing and evidence

**SYNTHETIC**

Supplied trace. Elapsed calendar intervals are not person-hours. Missing stage timing and evidence stay unknown. The scenario changes timing assumptions, not evidence statuses.

| Stage | Name | Evidence status | Queue hours | Work span hours | Scenario queue hours |
|---|---|---|---:|---:|---:|
| 1 | Intake | SUPPORTED | 0.133333 | 0.183333 | 0.133333 |
| 2 | Triage | SUPPORTED | 3.483333 | 0.300000 | 0.483333 |
| 3 | Need and acceptance | PARTIAL | 19.866667 | 0.833333 | 22.866667 |
| 4 | Design | SUPPORTED | 0.333333 | 0.750000 | 0.333333 |
| 5 | Implementation | SUPPORTED | 2.166667 | 21.450000 | 2.166667 |
| 6 | Peer review | SUPPORTED | 0.466667 | 1.866667 | 0.466667 |
| 7 | Verification | SUPPORTED | 0.100000 | 0.933333 | 0.100000 |
| 8 | User or business acceptance | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| 9 | Release authorization | SUPPORTED | 0.266667 | 0.133333 | 0.266667 |
| 10 | Deployment or activation | SUPPORTED | 0.066667 | 0.150000 | 0.066667 |
| 11 | Post-change validation | PARTIAL | 0.033333 | 0.083333 | 0.033333 |
| 12 | Support handoff | CONFLICT | 0.033333 | 0.366667 | 0.033333 |
| 13 | Follow-up and learning | SUPPORTED | 17.800000 | 0.533333 | 17.800000 |

## Observed endpoints and missing intervals

- SYN-041-001: observed endpoint span 72.333333 hours; scenario 72.333333 hours.
- Known queue sum 44.750000 hours; known work-span sum 27.583333 hours. Missing queue stages: 1; missing work spans: 1.

These are sums of supplied intervals and observed endpoints, not a complete critical-path model or a staffing-effort estimate. Overlapping stages could make sums exceed elapsed journey time.

## Unresolved evidence and follow-up

- Stage 3 (PARTIAL): Criterion AC-3 changed later; approval of revised wording is not in this artifact Where is the decision record approving revised AC-3?
- Stage 8 (UNKNOWN): Evidence absent; absence does not establish that acceptance did not happen Was acceptance required, and if so where is the authoritative record?
- Stage 11 (PARTIAL): Success criteria are undefined Which checks were required, what results were observed, and what would have triggered rollback?
- Stage 12 (CONFLICT): Timing of documentation readiness conflicts across sources Was a draft or internal note available before activation, and which record is authoritative?
- Stage 13 (SUPPORTED):  Where will completion evidence for the improvement action be retained?
