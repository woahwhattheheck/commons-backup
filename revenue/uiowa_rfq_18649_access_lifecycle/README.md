# UIOWA-053 — Human-access lifecycle evidence

Joiner, mover and leaver access across development and deployment environments: approvals,
entitlement reviews, emergency access, and whether an access change actually **reached the
systems it was supposed to reach**.

Offline, Python 3 standard library only.

## Status

| Thing | Status |
|---|---|
| `53-access-lifecycle-matrix.md` | **Deliverable.** The evidence matrix, generated. |
| `53-role-change-scenarios.md` | **Deliverable.** Fictional role-change scenarios for interviews, generated. |
| `access_lifecycle.py` | **Working code.** 43 tests, all passing. |
| `test_access_lifecycle.py` | **Working tests**, including every status and every refusal. |
| `fixtures/lifecycle_cases.json` | **FICTION.** Six invented episodes. |
| `examples/` | Generated JSON and CSV. |

Every case, person, role, system, ticket and date is invented. Nothing describes the
University of Iowa, no row is a finding, and no person is assessed anywhere.

## Run

```bash
python3 access_lifecycle.py
python3 access_lifecycle.py --matrix-out m.md --scenarios-out s.md --csv-out o.csv --json-out o.json
python3 -m unittest -v test_access_lifecycle.py
python3 -O -m unittest test_access_lifecycle.py
```

## How the completion bar is implemented

The bar is *"conclusions depend on lifecycle evidence rather than treating a written policy
as proof."* Evidence stages that cannot substitute for one another:

```
written_policy -> ticket_request -> approval_record -> execution_record -> system_state_observation
```

| evidence | establishes |
|---|---|
| `written_policy` | An intent exists. **Nothing about any individual case.** |
| `ticket_request` | A request was raised. |
| `approval_record` | An approval was recorded. |
| `execution_record` | Somebody recorded performing the change. Not that the system changed. |
| `system_state_observation` | The system's own state on a date, and what it showed. |
| `entitlement_review_record` | Standing access was reviewed on a date. Not that any change happened. |

Status per system: `NO_EVIDENCE`, `POLICY_ONLY`, `REQUESTED_ONLY`, `APPROVED_ONLY`,
`ACTION_RECORDED`, `CONFIRMED_IN_SYSTEM`, and `CONTRADICTED_IN_SYSTEM` — which outranks
every paper record.

Five mechanisms, each tested:

1. **A policy alone yields `POLICY_ONLY` and no conclusion.** Ten policies yield the same.
   Adding a policy to a request does not make it an approval.
2. **`POLICY_ONLY` is distinct from `NO_EVIDENCE`.** A standard that exists and was not
   followed up is a different conversation from no standard at all.
3. **A closed ticket is not a system state.** `ACTION_RECORDED`, never `CONFIRMED_IN_SYSTEM`.
4. **An observation before the change is excluded and listed.** A stale export is how a
   removal gets "confirmed" before it happened. An observation with no date is refused
   outright. An observation whose result was never recorded cannot confirm.
5. **Status is per system and never rolled up.** A case's status is its weakest system. An
   access change that reached three systems and missed a fourth has not been made.

Plus: when one system carries both a grant and a revoke, evidence that does not name which
it concerns is **excluded as ambiguous** rather than credited to whichever change is nearby.
An emergency elevation's audit entry says nothing about its later removal.

## Result over the synthetic set

```
6 cases, 13 system rows
system status: CONFIRMED_IN_SYSTEM=5  ACTION_RECORDED=2  POLICY_ONLY=3
               REQUESTED_ONLY=1  APPROVED_ONLY=1  CONTRADICTED_IN_SYSTEM=1
lifecycle events covered: 4 of 4
```

The two cases the order names:

- **`CASE-SYN-LEAVER-01`, contractor departure.** The identity account is
  `CONFIRMED_IN_SYSTEM` disabled. The source repository is `ACTION_RECORDED` — a closed
  ticket, nothing observed. The deployment pipeline carries a local account created outside
  the identity provider and is `POLICY_ONLY`: nobody has looked. Case status `POLICY_ONLY`.
  An aggregate "access removed" would have reported this departure as complete.
- **`CASE-SYN-MOVER-01`, changed responsibilities.** The new release-approver role is
  `CONFIRMED_IN_SYSTEM`, because somebody needed it to work. The tier 2 support role that is
  no longer required is `REQUESTED_ONLY` — a ticket raised and nothing after it. This is
  where entitlement accumulates.

Also carried: `CASE-SYN-LEAVER-02` (policy and nothing else — no conclusion possible),
`CASE-SYN-LEAVER-03` (the database still shows the role after a closed ticket, and a
pre-departure export was offered as proof and excluded), `CASE-SYN-EMERGENCY-01`
(elevation confirmed, retrospective approval absent, removal unobserved),
`CASE-SYN-JOINER-01` (the comparatively clean case, so the matrix is not only failures).

## Inputs still UNKNOWN

- Every case, system, ticket, date and record. All fictional.
- Which systems are actually in scope for a departure, and who decides that list.
- Whether accounts created outside the central identity provider are reachable by
  offboarding at all.
- What system-side evidence is retained, and for how long — `CASE-SYN-LEAVER-02` exists
  because a departure far enough back may have no records left.
- Whether entitlement reviews cover the systems the changes touch.
- A `CONFIRMED_IN_SYSTEM` status means one observation of one system matched the intent on
  one date. It is not a statement that access management works.

---

Built by seat OP5-CINDER (Claude Opus 5) for work order UIOWA-053.
