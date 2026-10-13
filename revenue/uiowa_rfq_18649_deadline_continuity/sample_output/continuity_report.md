# Research-deadline continuity (UIOWA-107)

**This scenario is fictional.** The deadline, the shared identity service,
the application change and every number below were invented for rehearsal.
It is not a University of Iowa finding, not a statement about University
capacity, and not a commitment to any date.

Scenario `UIOWA-107-SYNTHETIC-RIS-DEADLINE-001` — service RIS. Deadline: **Fictional research-administration reporting submission** (kickoff + 8 weeks; expressed relative to kickoff, never as a calendar appointment).

## Assumptions, stated in the open

| ID | Basis | Range (hours) | Statement | Stated by |
| --- | --- | --- | --- | --- |
| ASM-001 | ESTIMATED | 12–20 | effort to implement the scheduled application change | fictional RIS application lead |
| ASM-002 | UNKNOWN | — | coordination wait on the shared identity service's change-freeze window | UNKNOWN |
| ASM-003 | MEASURED | 32–40 | analyst capacity available inside the reporting window | fictional RIS roster export |
| ASM-004 | ESTIMATED | 4–6 | effort to rehearse and stage a rollback before the window | fictional RIS application lead |
| ASM-005 | ESTIMATED | 8–24 | unplanned recovery effort if the change misbehaves inside the window | fictional RIS application lead |
| ASM-006 | ASSUMED | 0–16 | temporary analyst capacity obtainable for the window | working figure; nobody has confirmed funding or availability |
| ASM-007 | MEASURED | 2–2 | coordination effort to defer the scheduled change by one cycle | fictional RIS change log |

**1 assumption(s) are UNKNOWN: ASM-002.** They carry no numbers. An UNKNOWN
input is not given a default or a midpoint — it propagates as an
unbounded range, and any conclusion resting on it comes out
`NOT_DETERMINED`. That is the honest answer.

## Preparation options

| Option | In-window exposure | Capacity | Verdict |
| --- | --- | --- | --- |
| **OPT-A** Proceed with the application change as scheduled | 20–UNBOUNDED | 32–40 | `NOT_DETERMINED` |
| **OPT-B** Defer the application change until after the reporting deadline | 2–2 | 32–40 | `FITS` |
| **OPT-C** Proceed, with a rehearsed rollback staged before the window | 16–UNBOUNDED | 32–40 | `NOT_DETERMINED` |
| **OPT-D** Proceed, and add temporary analyst capacity to the window | 20–UNBOUNDED | 32–56 | `NOT_DETERMINED` |

### OPT-A — Proceed with the application change as scheduled

Do the change in its planned slot and absorb whatever it costs inside the reporting window.

- Verdict `NOT_DETERMINED` — the ranges overlap or a bound is missing; not answerable yet
- Unanswerable because these inputs have no upper bound: `ASM-002`
- **Not modelled here:** the cost of the change itself slipping if the identity freeze turns out to be long

### OPT-B — Defer the application change until after the reporting deadline

Move the change one cycle. The reporting window sees only the coordination cost.

- Verdict `FITS` — the worst case still sits inside the capacity available in the window
- **Not modelled here:** the business cost of running the current application version for another cycle
- **Not modelled here:** whether anything downstream depends on the change landing in its original slot

### OPT-C — Proceed, with a rehearsed rollback staged before the window

Pay a known rehearsal cost up front so an in-window failure is a rollback rather than an unplanned recovery.

- Verdict `NOT_DETERMINED` — the ranges overlap or a bound is missing; not answerable yet
- Unanswerable because these inputs have no upper bound: `ASM-002`
- **Not modelled here:** whether a rollback is actually possible once the reporting run has started

### OPT-D — Proceed, and add temporary analyst capacity to the window

Leave the change where it is and widen the window's capacity instead.

- Verdict `NOT_DETERMINED` — the ranges overlap or a bound is missing; not answerable yet
- Unanswerable because these inputs have no upper bound: `ASM-002`
- **Not modelled here:** the ramp-up cost of a temporary analyst who does not know the reporting process

## Can the options be told apart?

### OPT-A vs OPT-B

- `SEPARATED` — OPT-B ends before OPT-A begins, so the comparison holds across the whole range
- Lower **in-window exposure**: `OPT-B`. That is a statement about hours
  inside the reporting window only — it is not a recommendation, and it
  does not price anything listed under *Not modelled*.

### OPT-A vs OPT-C

- `NOT_SEPARABLE` — the exposure ranges overlap; neither option is lower across the whole range
- **Evidence needed:** Obtain any upper bound for: coordination wait on the shared identity service's change-freeze window
  - Why: with no upper bound on this input, OPT-A and OPT-C cannot be compared at all

### OPT-A vs OPT-D

- `NOT_SEPARABLE` — the exposure ranges overlap; neither option is lower across the whole range
- **Evidence needed:** Confirm: temporary analyst capacity obtainable for the window
  - Why: OPT-A and OPT-D have identical in-window exposure; they differ only in capacity, and this ASSUMED input is the whole difference
- **Evidence needed:** Obtain any upper bound for: coordination wait on the shared identity service's change-freeze window
  - Why: with no upper bound on this input, OPT-A and OPT-D cannot be compared at all

### OPT-B vs OPT-C

- `SEPARATED` — OPT-B ends before OPT-C begins, so the comparison holds across the whole range
- Lower **in-window exposure**: `OPT-B`. That is a statement about hours
  inside the reporting window only — it is not a recommendation, and it
  does not price anything listed under *Not modelled*.

### OPT-B vs OPT-D

- `SEPARATED` — OPT-B ends before OPT-D begins, so the comparison holds across the whole range
- Lower **in-window exposure**: `OPT-B`. That is a statement about hours
  inside the reporting window only — it is not a recommendation, and it
  does not price anything listed under *Not modelled*.

### OPT-C vs OPT-D

- `NOT_SEPARABLE` — the exposure ranges overlap; neither option is lower across the whole range
- **Evidence needed:** Obtain any upper bound for: coordination wait on the shared identity service's change-freeze window
  - Why: with no upper bound on this input, OPT-C and OPT-D cannot be compared at all

## What this tool does not do

- It never marks an option recommended. It narrows the question and names
  what to go find out; a person decides.
- It does not rank teams, units or people. The comparison is between
  preparation options.
- It runs no load test and reads no live system. Availability is a stated
  scenario assumption, never an appointment or a commitment.

## Still UNKNOWN (University inputs not collected)

- the real research-administration reporting calendar and its true cutoff
- whether the shared identity service publishes a change-freeze window at all
- who is empowered to defer a scheduled application change, and on what notice
- actual analyst capacity in the reporting window, as opposed to roster headcount
- whether temporary capacity is fundable at all in that period
