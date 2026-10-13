# Access-lifecycle evidence matrix

**SYNTHETIC.** Every case, person, system and record below is fictional, written to exercise the review method. Nothing here describes the University of Iowa, and no row is a finding.

## What each evidence kind establishes

| evidence | establishes |
|---|---|
| `written_policy` | That an intent exists. **Nothing about any individual case.** |
| `ticket_request` | That a request was raised. |
| `approval_record` | That an approval was recorded. |
| `execution_record` | That somebody recorded performing the change. Not that the system changed. |
| `system_state_observation` | That the system's own state was observed on a date, and what it showed. |
| `entitlement_review_record` | That standing access was reviewed on a date. Not that any particular change happened. |

A stage never establishes what a later stage establishes. The order is the method: `written_policy` → `ticket_request` → `approval_record` → `execution_record` → `system_state_observation`.

## Status vocabulary

| status | meaning |
|---|---|
| `CONFIRMED_IN_SYSTEM` | The system's own state was observed after the change and matches the intent. |
| `ACTION_RECORDED` | Somebody recorded performing the change. The system's own state has not been observed since, so whether it took effect is unverified. |
| `APPROVED_ONLY` | An approval is recorded. Nobody has evidenced that the change was performed or reached the system. |
| `REQUESTED_ONLY` | A request exists. Nobody has evidenced that it was approved, performed, or reached the system. |
| `POLICY_ONLY` | Only a written policy applies. A policy states an intent; it is not evidence about this case, and no conclusion about this case rests on it. |
| `NO_EVIDENCE` | Nothing is recorded for this system. Not a failure and not a pass -- an open question. |
| `CONTRADICTED_IN_SYSTEM` | The system's own state was observed after the change and does NOT match the intent. This outranks every paper record. |

## The matrix

6 cases, 13 system rows. **Status is per system.** A case's status is its weakest system, never an average — an access change that reached three systems and missed a fourth has not been made.

| case | event | system | env | intent | status | what would settle it |
|---|---|---|---|---|---|---|
| `CASE-SYN-LEAVER-01` | leaver | central identity provider | shared | revoke | **CONFIRMED_IN_SYSTEM** | — |
| `CASE-SYN-LEAVER-01` | leaver | source repository | development | revoke | **ACTION_RECORDED** | Request this system's own state as at a date after 2026-08-31: an export or account listing showing whether the revoke took effect. |
| `CASE-SYN-LEAVER-01` | leaver | deployment pipeline | deployment | revoke | **POLICY_ONLY** | No case-specific evidence establishes anything about this system. A written policy is an intent, not a record of what happened here. |
| `CASE-SYN-MOVER-01` | mover | deployment pipeline | deployment | grant | **CONFIRMED_IN_SYSTEM** | — |
| `CASE-SYN-MOVER-01` | mover | support console | production support | revoke | **REQUESTED_ONLY** | Request this system's own state as at a date after 2026-07-01: an export or account listing showing whether the revoke took effect. |
| `CASE-SYN-JOINER-01` | joiner | central identity provider | shared | grant | **CONFIRMED_IN_SYSTEM** | — |
| `CASE-SYN-JOINER-01` | joiner | source repository | development | grant | **CONFIRMED_IN_SYSTEM** | — |
| `CASE-SYN-EMERGENCY-01` | emergency_access | deployment pipeline | deployment | grant | **CONFIRMED_IN_SYSTEM** | — |
| `CASE-SYN-EMERGENCY-01` | emergency_access | deployment pipeline | deployment | revoke | **ACTION_RECORDED** | Request this system's own state as at a date after 2026-08-13: an export or account listing showing whether the revoke took effect. |
| `CASE-SYN-LEAVER-02` | leaver | central identity provider | shared | revoke | **POLICY_ONLY** | No case-specific evidence establishes anything about this system. A written policy is an intent, not a record of what happened here. |
| `CASE-SYN-LEAVER-02` | leaver | reporting database | production support | revoke | **POLICY_ONLY** | No case-specific evidence establishes anything about this system. A written policy is an intent, not a record of what happened here. |
| `CASE-SYN-LEAVER-03` | leaver | central identity provider | shared | revoke | **APPROVED_ONLY** | Request this system's own state as at a date after 2026-09-05: an export or account listing showing whether the revoke took effect. |
| `CASE-SYN-LEAVER-03` | leaver | reporting database | production support | revoke | **CONTRADICTED_IN_SYSTEM** | The system's state does not match the intent. Establish whether the change was reversed, never applied, or applied to a different account. |

## Case summary

| case | event | worker | case status | systems not confirmed |
|---|---|---|---|---|
| `CASE-SYN-LEAVER-01` | leaver | contractor | **POLICY_ONLY** | source repository, deployment pipeline |
| `CASE-SYN-MOVER-01` | mover | staff | **REQUESTED_ONLY** | support console |
| `CASE-SYN-JOINER-01` | joiner | staff | **CONFIRMED_IN_SYSTEM** | none |
| `CASE-SYN-EMERGENCY-01` | emergency_access | staff | **ACTION_RECORDED** | deployment pipeline |
| `CASE-SYN-LEAVER-02` | leaver | staff | **POLICY_ONLY** | central identity provider, reporting database |
| `CASE-SYN-LEAVER-03` | leaver | staff | **CONTRADICTED_IN_SYSTEM** | central identity provider, reporting database |

## Evidence excluded as stale

An observation taken before the change cannot show the change reached the system. These were excluded from the conclusion and are listed rather than dropped.

| case | system | observed | change effective | excluded because |
|---|---|---|---|---|
| `CASE-SYN-LEAVER-03` | central identity provider | 2026-09-01 | 2026-09-05 | observed before the change took effect, so it cannot show the change reached the system |

## Limits

- Every case, system, role and record here is fictional. Nothing describes the University of Iowa, and no output is a finding.
- A CONFIRMED_IN_SYSTEM status means one observation of one system matched the intent on one date. It is not a statement that access management works.
- A written policy establishes nothing about any individual case, and no status in this output is derived from one.
- No person is assessed. The subject of every conclusion is a system's recorded state, never an individual's performance.
