# UIOWA-108 — Contractor-transition evidence demonstration

Solicitation 18649. Work order UIOWA-108: *"Connect synthetic staff-role
changes, application ownership, service identities, and runbook updates into
one realistic handoff scenario … The example distinguishes completed access
changes, unresolved ownership, and missing evidence without inserting real
account data."*

Built by seat `OP5-KELVIN` (Claude · Opus 5). Python 3 standard library only,
no network at runtime, deterministic. Completion-integrity work by R9V6 and
Trellis, partial-action semantics by MERIDIAN-Q7, output preservation by
6D9F-R3; integrated by yZ-HELIOTROPE-7C.

---

## Everything here is fictional

Every person, application, service identity, runbook and change record in
`fixtures/` was invented for rehearsal. **This is not a University of Iowa
finding** and says nothing about University access practice. The packet
carries `authority: FICTIONAL_REHEARSAL_ONLY` and the same
`prohibited_interpretation` list as the collection landed for UIOWA-091, so a
downstream tool reading it cannot mistake it for evidence.

Still **UNKNOWN**, listed as evidence to collect later:

- the real joiner/mover/leaver process and who authorises each step
- whether service identities are inventoried anywhere authoritative
- how contractor end dates reach the access-management system, if they do
- what evidence the University can actually export for a completed revocation
- who owns a runbook when its author leaves

---

## The three states, and why they must not merge

A handoff report that collapses these into one green checkmark is worse than
no report, because it is confidently wrong about the one thing somebody will
rely on it for.

| State | Means | Next action |
| --- | --- | --- |
| `COMPLETED` | the supplied dated change records have evidence locators and no remaining recorded blocker | retain the locators; this is not external verification |
| `UNRESOLVED_OWNERSHIP` | the departing contractor still owns it and **no successor is recorded** | name an accountable owner before the last day — this is a live gap |
| `NO_EVIDENCE` | no record establishes either outcome | ask for the change record or export that would settle it |

The distinction that does the most work is between the second and third.
**Unresolved ownership is knowledge** — we know exactly what is wrong and who
is not covering it. **No evidence is the absence of knowledge.** They need
different conversations, and a report that merges them sends the wrong one.

Two cases in the fixture are there because they are the common ways a handoff
report lies:

- **`SYN-RB-001` is marked `COMPLETED` with nothing attached.** Somebody typed
  a word into a status field. That is not evidence, so it classifies
  `NO_EVIDENCE`.
- **`SYN-SVC-002` has a successor named and a request raised.** A named
  successor is a *plan*. Nothing shows the handoff occurred, so it classifies
  `NO_EVIDENCE` too.

### Closure is fail-closed, and there is no percentage

`transition_closed` is true only when **every** item is `COMPLETED` and no
packet issues remain. There is no threshold, weighting or completion
percentage. An empty packet does not close by vacuous truth either — nothing
to check is not the same as everything checked.

Completed actions retain their evidence locators while a missing/self
successor or a separate pending action keeps the handoff open. Duplicate
change IDs retain every occurrence's target and subject relationships; the
first indexed occurrence cannot hide another affected item. Integrity
problems propagate through related records rather than being disconnected
from their completion decisions.

Completed records require an actual ISO calendar date or offset-bearing
timestamp. Malformed record structures return a controlled input error;
invalid fields, references and completion dates remain explicit diagnostics.
These checks describe the supplied fictional records, not whether an event
actually occurred.

---

## The realism guard: "without inserting real account data"

A contractor-transition packet is exactly where real-looking account data
leaks into a deliverable. So this is a **hard refusal, not a convention**. Any
of these makes the whole packet undeliverable and the CLI renders nothing:

| Code | Refuses |
| --- | --- |
| `REAL_LOOKING_EMAIL` | any address not under the reserved `.invalid` TLD |
| `REAL_LOOKING_ACCOUNT_NAME` | any `account_name` not prefixed `syn-` |
| `IDENTIFIER_NOT_MARKED_SYNTHETIC` | any id not matching `SYN-<KIND>-<NNN>` |
| `RECORD_NOT_MARKED_SYNTHETIC` | any record not declaring `synthetic: true` |
| `POSSIBLE_REAL_ID_NUMBER` | any nine-digit run in any string field |

`.invalid` is reserved by RFC 2606 precisely so it can never resolve to a real
host — a fictional address under any other TLD is one somebody might actually
try.

These checks recognize documented shapes, not every possible kind of personal
information. Do not insert real account data into the rehearsal. Programmatic
callers must consult `scenario.is_deliverable(issues)` before distributing a
report; lower-level renderers are not a redaction service.

**Safety and integrity are treated differently on purpose.** A broken
reference is a *finding* — the report still renders so somebody can see it.
Real-looking account data must not leave the building, so the report refuses
to render at all rather than degrading gracefully.

---

## Run it

```sh
cd revenue/uiowa_rfq_18649_contractor_transition

python3 transition.py --input fixtures/contractor_transition.json --outdir out
python3 transition.py --input fixtures/contractor_transition.json --print
```

Exit codes are a contract: **0** transition closed · **1** report produced,
open items or packet issues remain · **2** bad input or output publication
failed · **3** refused, packet contains unsafe content.

`--outdir` creates `transition_items.csv`, `transition_report.json` and
`transition_report.md`. Existing empty directories and unrelated files are
supported. Any existing target name, including a symbolic link or input
alias, is refused without overwriting it. Choose a fresh destination for a
later run. Output failures produce a clear diagnostic and exit 2; cleanup
removes only files created by that invocation whose identities still match.
This is not an atomic directory installation: consume the bundle only after
the command finishes with exit 0 or 1.

Partial files can be observable during writing. Failed cleanup can leave
partial artifacts, and created directories may remain after a refusal. No
power-loss or adversarial-filesystem guarantee is provided. The create-only
contract belongs to the CLI's `publish_artifacts` path, not the older
low-level `write_csv` helper. Do not delete previous evidence to make a later
invocation succeed; select a new destination.

Measured on the synthetic packet:

```
items=6 completed=2 unresolved=2 no_evidence=2 closed=False issues=0
```

Two clean completions with synthetic evidence locators (the strength), two
items without a successor and two where the record does not support the
outcome claimed (the gaps).

---

## Files

| File | What it is |
| --- | --- |
| `scenario.py` | packet schema, the realism guard, referential integrity |
| `transition.py` | the three-state classifier, report renderers, CLI |
| `fixtures/contractor_transition.json` | the coherent fictional scenario — 3 people, 2 applications, 2 service identities, 2 runbooks, 4 change records |
| `sample_output/` | retained fictional example output |

## What is working vs. draft

**Working demonstration.** The three-state classifier, conservative closure,
realism guard, referential integrity, all three output formats and controlled
CLI outcomes. The existing fictional packet is the runnable example; current
swarm rules use product execution rather than new test or receipt packages.

**Draft, pending real evidence.** The scenario is fiction. What counts as an
acceptable evidence locator for a completed revocation at the University is
unknown, and the `evidence_ref`-required rule should be confirmed against what
their systems can actually export before it classifies a real transition.

The supplied inventory is not proved exhaustive. The tool does not fetch or
authenticate a locator, establish that a declared action happened, or verify
any real person's access. It does not infer that one historical request
supersedes another; the packet author must reconcile those records explicitly.

**Implementation history.** [Integration #19233](https://github.com/woahwhattheheck/commons/pull/19233)
combined the contributions discussed in [#16359](https://github.com/woahwhattheheck/commons/pull/16359),
[#16363](https://github.com/woahwhattheheck/commons/pull/16363) and
[#16417](https://github.com/woahwhattheheck/commons/pull/16417).
Historical tests, replay logs and donor patches remain in Git history and
those discussions, not in the current operator package.

## Scope

This lane produces a worked demonstration. It does not score anyone, rate a
unit's maturity, certify anything, or evaluate an individual — records are
keyed to roles and systems, never to a named person. Join keys (`service` ∈
ESS/RIS/IAM, `synthetic: true`, `authority: FICTIONAL_REHEARSAL_ONLY`,
`synthetic://` locators) match the collection landed for UIOWA-091; this lane
emits those keys and writes into no other lane's files.
