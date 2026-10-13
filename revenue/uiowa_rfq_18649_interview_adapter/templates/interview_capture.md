# Interview capture template

One session, several participants. Copy this per session; the adapter reads the JSON form
(`session.schema.json`) and this page is the human sheet it mirrors field for field.

**Participants are recorded as ROLES.** There is no field for a person's name, and the loader
refuses a file that carries one rather than stripping it.

## Session header

| Field | Value |
|---|---|
| `session_id` | |
| `group` | ESS / RIS / IAM |
| `session_source_id` | the source-register id for these notes themselves |
| `recorded_by_role` | |

## Participants

| `participant_id` | `role` | `group` |
|---|---|---|
| P1 | | |
| P2 | | |

## Questions

| `question_id` | `assessment_area` | `text` |
|---|---|---|
| Q1 | | |

## Notes — one row per participant per question

| Field | What goes in it |
|---|---|
| `note_id` | |
| `participant_id` | which role said it |
| `question_id` | |
| `stated_practice` | what they said the practice is |
| `concrete_example` | a **specific instance**, with its identifier if there is one. "We generally do X" is a habit, not an instance, and will not raise the note above `STATED`. |
| `corroborating_artifact` | a `source_id` from the register — a record the **practice** produced. An interview record cannot corroborate interview testimony. |
| `disagrees_with` | another `note_id`, if this contradicts it. Record it from whichever side noticed; the adapter marks both. |
| `follow_up` | what to ask or request next |

## What the adapter will do with each note

| Status | When | May support a finding |
|---|---|---|
| `STATED` | testimony only | no |
| `ILLUSTRATED` | + a specific example | no |
| `CORROBORATED` | + an artifact that resolves in the register | **yes** |
| `DISPUTED` | another participant contradicts it | no — both sides retained, not adjudicated |

A question a participant did not answer is recorded as **not covered**. That is absence of
evidence about the practice, not evidence of a gap in it.
