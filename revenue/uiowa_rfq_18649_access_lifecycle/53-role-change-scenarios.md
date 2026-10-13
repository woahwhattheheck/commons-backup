# Fictional role-change scenarios for interviews

**SYNTHETIC.** These scenarios are invented. They are prompts for a conversation, not findings, and not descriptions of anything observed.

Each scenario states what the evidence establishes, what it does not, and the questions that would close the gap. The questions ask for **records**, because a description of the process is not evidence about the case.

## `CASE-SYN-LEAVER-01` — Contractor departure at end of engagement

*Event:* leaver · *Worker:* contractor · *Role:* Integration developer (fictional) · *Date:* 2026-08-31

**Case status: `POLICY_ONLY`** — the weakest system is deployment pipeline at POLICY_ONLY. The case status is the weakest system, not an average: an access change that reached three systems and missed a fourth has not been made.

| system | intent | status |
|---|---|---|
| central identity provider | revoke | `CONFIRMED_IN_SYSTEM` |
| source repository | revoke | `ACTION_RECORDED` |
| deployment pipeline | revoke | `POLICY_ONLY` |

**What to ask for:**

- *source repository* — Request this system's own state as at a date after 2026-08-31: an export or account listing showing whether the revoke took effect.
- *deployment pipeline* — No case-specific evidence establishes anything about this system. A written policy is an intent, not a record of what happened here.

**Interview prompts:**

- For this departure, which systems were in scope, and who decided the list?
- How are accounts created outside the identity provider brought into offboarding?
- Can you show the pipeline's own account listing as at a date after 31 August?

*Note:* The case the order names. The central identity account was confirmed disabled; the deployment pipeline carries a separate local account that nobody has looked at. An aggregate 'access removed' would have hidden that entirely.

## `CASE-SYN-MOVER-01` — Changed responsibilities: new access granted, previous access not evidenced as removed

*Event:* mover · *Worker:* staff · *Role:* Moved from application support to release engineering (fictional) · *Date:* 2026-07-01

**Case status: `REQUESTED_ONLY`** — the weakest system is support console at REQUESTED_ONLY. The case status is the weakest system, not an average: an access change that reached three systems and missed a fourth has not been made.

| system | intent | status |
|---|---|---|
| deployment pipeline | grant | `CONFIRMED_IN_SYSTEM` |
| support console | revoke | `REQUESTED_ONLY` |

**What to ask for:**

- *support console* — Request this system's own state as at a date after 2026-07-01: an export or account listing showing whether the revoke took effect.

**Interview prompts:**

- When somebody changes team, what triggers the removal of the entitlements they no longer need?
- Is the removal tracked to completion, or closed when the new access is working?
- Can you show the support console's role listing for this person as at any date after 1 July?

*Note:* The second case the order names. Movers are where entitlement accumulates: the grant is confirmed because somebody needed it to work, and the revoke has a request and nothing after it.

## `CASE-SYN-JOINER-01` — New starter, development environments only

*Event:* joiner · *Worker:* staff · *Role:* Application developer (fictional) · *Date:* 2026-06-01

**Case status: `CONFIRMED_IN_SYSTEM`** — the weakest system is central identity provider at CONFIRMED_IN_SYSTEM. The case status is the weakest system, not an average: an access change that reached three systems and missed a fourth has not been made.

| system | intent | status |
|---|---|---|
| central identity provider | grant | `CONFIRMED_IN_SYSTEM` |
| source repository | grant | `CONFIRMED_IN_SYSTEM` |

**Interview prompts:**

- How soon after a start date is access checked against what was approved?
- Who owns the approval for repository access, and is it separate from the identity account?

*Note:* The comparatively clean case. Both systems observed after the change; included so the matrix is not only failures.

## `CASE-SYN-EMERGENCY-01` — Emergency elevation used during an incident; retrospective approval not evidenced

*Event:* emergency_access · *Worker:* staff · *Role:* On-call engineer (fictional) · *Date:* 2026-08-12

**Case status: `ACTION_RECORDED`** — the weakest system is deployment pipeline at ACTION_RECORDED. The case status is the weakest system, not an average: an access change that reached three systems and missed a fourth has not been made.

| system | intent | status |
|---|---|---|
| deployment pipeline | grant | `CONFIRMED_IN_SYSTEM` |
| deployment pipeline | revoke | `ACTION_RECORDED` |

**What to ask for:**

- *deployment pipeline* — Request this system's own state as at a date after 2026-08-13: an export or account listing showing whether the revoke took effect.

**Interview prompts:**

- What record is created when emergency elevation is used, and who reviews it?
- Can you show the retrospective approval for the 12 August elevation?
- How is the elevated role removed after the incident, and is its removal observed?

*Note:* Emergency access is the path designed to bypass the approval gate. The elevation is confirmed in the system; the retrospective approval the standard requires has no record at all, and the removal has only an audit-log entry with no later observation. Both changes sit on ONE system, so each piece of evidence has to name which change it concerns -- evidence that does not is excluded as ambiguous rather than credited to whichever change is nearby.

## `CASE-SYN-LEAVER-02` — Departure where the only applicable evidence is the written standard

*Event:* leaver · *Worker:* staff · *Role:* Analyst (fictional) · *Date:* 2026-05-29

**Case status: `POLICY_ONLY`** — the weakest system is central identity provider at POLICY_ONLY. The case status is the weakest system, not an average: an access change that reached three systems and missed a fourth has not been made.

| system | intent | status |
|---|---|---|
| central identity provider | revoke | `POLICY_ONLY` |
| reporting database | revoke | `POLICY_ONLY` |

**What to ask for:**

- *central identity provider* — No case-specific evidence establishes anything about this system. A written policy is an intent, not a record of what happened here.
- *reporting database* — No case-specific evidence establishes anything about this system. A written policy is an intent, not a record of what happened here.

**Interview prompts:**

- For a departure in May, what records would still exist today?
- Where are offboarding tickets retained, and for how long?
- If no ticket exists, is there any system-side record that would show when the account was disabled?

*Note:* The refusal case. There is a policy and nothing else, so no conclusion about this departure can be drawn at all. The policy is not weak evidence here; it is evidence about a different subject.

## `CASE-SYN-LEAVER-03` — Departure where the system state contradicts the closed ticket, and a stale export was offered as proof

*Event:* leaver · *Worker:* staff · *Role:* Database administrator (fictional) · *Date:* 2026-09-05

**Case status: `CONTRADICTED_IN_SYSTEM`** — the weakest system is reporting database at CONTRADICTED_IN_SYSTEM. The case status is the weakest system, not an average: an access change that reached three systems and missed a fourth has not been made.

| system | intent | status |
|---|---|---|
| central identity provider | revoke | `APPROVED_ONLY` |
| reporting database | revoke | `CONTRADICTED_IN_SYSTEM` |

**What to ask for:**

- *central identity provider* — Request this system's own state as at a date after 2026-09-05: an export or account listing showing whether the revoke took effect.
- *reporting database* — The system's state does not match the intent. Establish whether the change was reversed, never applied, or applied to a different account.

**Interview prompts:**

- The database still shows this role. Was the change reversed, never applied, or applied to a different account?
- What date does the supplied directory export cover, and is there one from after the departure?
- Does the quarterly entitlement review cover the reporting database's administrative roles?

*Note:* Two mechanisms at once. The reporting database still shows the account after the departure, which outranks the closed ticket. And an export taken before the departure was offered as evidence for the identity provider; it is excluded and listed, because it cannot show a later change.

---

No person is assessed by any scenario above. The subject is always a system's recorded state, never an individual's performance.
