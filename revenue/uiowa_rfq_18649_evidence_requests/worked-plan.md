# Evidence request budget scenarios

deterministic marginal-priority-per-minute greedy heuristic; not an optimum certificate

Potential question coverage only. Selection does not resolve evidence or authorize collection.

## 60 minutes

Uses 50 minutes; covers 3 questions with total editable priority 11.

| Step | Request | Minutes | New priority | New questions |
| --- | --- | ---: | ---: | --- |
| 1 | request:EV-SYN-IAM-DEP-POL-004 | 30 | 8 | conflict:CG-SYN-IAM-DEP-01, follow-up:EV-SYN-IAM-DEP-POL-004 |
| 2 | request:EV-SYN-ESS-SD-INT-001 | 20 | 3 | follow-up:EV-SYN-ESS-SD-INT-001 |

Unselected requests:

- `request:EV-SYN-ESS-AI-INV-006`: EFFORT_UNESTIMATED
- `request:EV-SYN-ESS-SD-CFG-002`: REMAINING_BUDGET
- `request:EV-SYN-IAM-DEP-CHG-005`: REMAINING_BUDGET
- `request:EV-SYN-RIS-AI-SRCH-007`: REMAINING_BUDGET
- `request:EV-SYN-RIS-SEC-POL-003`: REMAINING_BUDGET

## 120 minutes

Uses 90 minutes; covers 4 questions with total editable priority 14.

| Step | Request | Minutes | New priority | New questions |
| --- | --- | ---: | ---: | --- |
| 1 | request:EV-SYN-IAM-DEP-POL-004 | 30 | 8 | conflict:CG-SYN-IAM-DEP-01, follow-up:EV-SYN-IAM-DEP-POL-004 |
| 2 | request:EV-SYN-ESS-SD-INT-001 | 20 | 3 | follow-up:EV-SYN-ESS-SD-INT-001 |
| 3 | request:EV-SYN-IAM-DEP-CHG-005 | 40 | 3 | follow-up:EV-SYN-IAM-DEP-CHG-005 |

Unselected requests:

- `request:EV-SYN-ESS-AI-INV-006`: EFFORT_UNESTIMATED
- `request:EV-SYN-ESS-SD-CFG-002`: REMAINING_BUDGET
- `request:EV-SYN-RIS-AI-SRCH-007`: REMAINING_BUDGET
- `request:EV-SYN-RIS-SEC-POL-003`: REMAINING_BUDGET

## 240 minutes

Uses 210 minutes; covers 6 questions with total editable priority 21.

| Step | Request | Minutes | New priority | New questions |
| --- | --- | ---: | ---: | --- |
| 1 | request:EV-SYN-IAM-DEP-POL-004 | 30 | 8 | conflict:CG-SYN-IAM-DEP-01, follow-up:EV-SYN-IAM-DEP-POL-004 |
| 2 | request:EV-SYN-ESS-SD-INT-001 | 20 | 3 | follow-up:EV-SYN-ESS-SD-INT-001 |
| 3 | request:EV-SYN-IAM-DEP-CHG-005 | 40 | 3 | follow-up:EV-SYN-IAM-DEP-CHG-005 |
| 4 | request:EV-SYN-RIS-AI-SRCH-007 | 60 | 4 | follow-up:EV-SYN-RIS-AI-SRCH-007 |
| 5 | request:EV-SYN-RIS-SEC-POL-003 | 60 | 3 | follow-up:EV-SYN-RIS-SEC-POL-003 |

Unselected requests:

- `request:EV-SYN-ESS-AI-INV-006`: EFFORT_UNESTIMATED
- `request:EV-SYN-ESS-SD-CFG-002`: REMAINING_BUDGET

