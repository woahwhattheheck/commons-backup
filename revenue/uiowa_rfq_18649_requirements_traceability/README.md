# UIOWA-042 — Requirements-to-acceptance traceability

Solicitation 18649. Work order UIOWA-042: *"Design a practical way to connect
business requests, acceptance criteria, implementation records, tests, and
user acceptance across different delivery styles … Examples include a changed
requirement and incomplete acceptance evidence, with explicit follow-up
questions rather than invented conclusions."*

Built by seat `OP5-KELVIN` (Claude · Opus 5). Python 3 standard library only,
no network, no clock, deterministic.

## Everything here is fictional

Every request, criterion, implementation, test and acceptance record in
`fixtures/` was invented for rehearsal. **Not a University of Iowa finding**
and not a statement about University delivery practice. No individual is
named — acceptance is recorded by role.

## The chain

```
request → acceptance criterion → implementation → test → user acceptance
```

A criterion closes only when every link resolves **and** the acceptance is
recorded against that criterion's **current revision**.

| State | Meaning |
| --- | --- |
| `TRACED` | every link resolves, accepted at the current revision |
| `ACCEPTED_AGAINST_SUPERSEDED_REVISION` | acceptance exists, but against an earlier revision |
| `INCOMPLETE_ACCEPTANCE` | no acceptance record, or one with no evidence behind it |
| `TEST_NOT_PASSING` | a test exists but failed or was never run |
| `UNTESTED` | implemented, no test and no declared regression coverage |
| `NOT_IMPLEMENTED` | no implementation references this criterion |
| `BROKEN_LINK` | a record points at something not in this example |
| `SUPERSEDED` | replaced; its successor carries the requirement |

## The two cases the order requires

**A changed requirement.** `AC-100-01` is at revision 2 — the retention window
moved from three days to seven during delivery. Its acceptance was recorded
against revision 1. A spreadsheet shows a tick in that row. What the records
actually say is that somebody accepted an *earlier version* of the
requirement, and nobody has accepted this one. The state is
`ACCEPTED_AGAINST_SUPERSEDED_REVISION` and the follow-up is *"ask who accepted
revision 2 … do not carry the earlier acceptance forward."*

**Incomplete acceptance evidence.** Two flavours, both present:
`AC-100-02` has passing tests and no acceptance record at all; `AC-100-09` has
an acceptance row with no locator behind it. A passing test is evidence the
code does what the test says. It is not evidence anybody agreed that was the
need, and the follow-up says so.

Neither is resolved by this tool. The verdict stays `NOT_ESTABLISHED` until a
person closes them.

## Delivery styles

A **maintenance change** may satisfy the test link with declared regression
coverage (`covered_by_regression_ref`) instead of a dedicated test — but only
because the record *says* so. With no locator it is `UNTESTED`; the tool never
assumes an existing suite covers a change. A **project** cannot use that
shortcut at all. Both behaviours are asserted.

## Measured on the two examples

```
examples=2 criteria=11 open=6 verdicts=EVIDENCED,NOT_ESTABLISHED
```

The maintenance change traces completely (including the declared-coverage
path). The project does not, and the six open rows each carry the question
that would close them. There is **no completion percentage** — a figure that
averaged `TRACED` against `ACCEPTED_AGAINST_SUPERSEDED_REVISION` would hide
the only thing worth knowing.

## Run it

```sh
cd revenue/uiowa_rfq_18649_requirements_traceability

python3 trace.py --input fixtures/maintenance_change.json fixtures/project_delivery.json --outdir out
python3 trace.py --input fixtures/project_delivery.json --print
python3 prompts.py --guide
python3 prompts.py --for fixtures/project_delivery.json
python3 -m unittest -v test_trace
```

Exit codes: **0** every criterion closed · **1** open criteria remain ·
**2** bad input.

## Interview prompts

`prompts.py` walks the chain once per delivered change — every stage has a
question, asserted by test. Each prompt asks for something that exists (a
locator, a role, a date, an instance) and is explicitly answerable with "I
don't know", recorded as `UNKNOWN` rather than estimated. `self_rating`,
`quality_score`, `peer_comparison` and `individual_performance` are a banned
set and a test walks every prompt to enforce it. Probes fire from observed
states, so a clean example draws none.

## Files

| File | What it is |
| --- | --- |
| `trace.py` | the chain, the eight states, follow-ups, renderers, CLI |
| `prompts.py` | interview prompts and the probe generator |
| `fixtures/maintenance_change.json` | small change, 2 criteria, traces completely |
| `fixtures/project_delivery.json` | larger project, 9 criteria, contains both required cases |
| `sample_output/` | committed output; a test fails if it drifts from the code |
| `test_trace.py` | 43 unittest cases |

## What is working vs. draft

**Working and tested.** All eight states and their decision paths, revision
comparison, the delivery-style rule in both directions, broken-reference
detection, the verdict, the probe generator, all three output files and the
CLI error paths.

**Draft, pending real evidence.** Both examples are fiction. The rule that an
acceptance must cite the criterion revision it was given against is the load
-bearing assumption here, and it only works if that field exists in whatever
system records acceptance. Whether it does is unknown.

## Still UNKNOWN

- where business requests are recorded, and whether acceptance criteria live with them
- who is empowered to accept delivered work, by role
- whether acceptance is recorded at all for maintenance changes
- what happens to a recorded acceptance when the requirement later changes
- whether regression coverage is asserted anywhere a locator could be read from
