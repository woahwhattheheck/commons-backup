# UIOWA-071 — Current AI-use inventory

Solicitation 18649. Work order UIOWA-071: *"Design a discovery instrument for AI
already used in development, documentation, testing, support, and analysis …
The inventory separates active use, informal experiments, and planned use;
interview questions seek concrete examples and leave unsupported University
adoption claims unfilled."*

Built by seat `OP5-KELVIN` (Claude · Opus 5). Python 3 standard library only.
No network at runtime, no model calls, no installed packages. The same input
always produces the same output.

---

## Everything here is fictional

The record collections under `fixtures/` were written to rehearse the
instrument. **They do not describe the University of Iowa.** No University
input has been collected by this lane. Every fictional source locator uses the
`synthetic://` scheme so a rehearsal record can never be mistaken for a real
one, and the rendered report states its own synthetic status on the first
screen.

What is still **UNKNOWN**, and stays UNKNOWN until real evidence is collected:

- which units actually use AI tooling today, and under what approval
- whether any use touches student or restricted data, and under which access
  semantics
- existing license, contract or procurement coverage for any tool named
- whether informal experiments are known to the unit's leadership
- the real headcount behind any role named in an entry

None of those is reported as a zero, a pass, or a low rating.

---

## What it does

`inventory.py` classifies each captured AI use into exactly one of five
buckets, from what the record can *show* rather than from what it *asserts*:

| Bucket | Meaning |
| --- | --- |
| `ACTIVE_USE` | running work, with a concrete example behind it |
| `INFORMAL_EXPERIMENT` | real use, but not an operated workflow |
| `PLANNED_USE` | intended; nothing observed yet |
| `UNSUPPORTED_CLAIM` | use asserted, nothing demonstrates it |
| `UNKNOWN` | not enough captured to classify |

The five are reported separately and are **never** combined into an adoption
percentage, a maturity level, or a peer comparison. A test asserts the buckets
sum to the record count, so no bucket can quietly absorb a row.

### The three rules that carry the order's intent

**1. A claim of use with no concrete example never becomes active use.**
A concrete example means an evidence locator, a benefit with an example behind
it, or a named output. With none of the three, the record goes to
`UNSUPPORTED_CLAIM` and is counted there in the open. This is the whole point:
an AI-use inventory is the easiest place in an assessment to manufacture an
adoption number — somebody says "we use AI for testing", it lands in a cell,
and three documents later it is a finding with nothing behind it.

**2. The classifier demotes, and records why; it never promotes.**
A record declared `ACTIVE` that reports an occasional cadence, no named output,
or no integration is recorded as an experiment *with the reason attached and a
`demoted` flag set* — never silently. Conversely a record declared `PLANNED`
that turns up carrying an output is **not** reclassified as active: it stays
`PLANNED_USE` and raises `STATUS_EVIDENCE_MISMATCH` with both readings
preserved for a human, the same treatment conflicting sources get in
`../uiowa_rfq_18649_workshare/methodology/23-evidence-confidence.md`.

**3. A blank answer is UNKNOWN, and an explicit "none" is a different answer.**
Blank frequency does not become "never". Blank integrations does not become
"standalone". Blank headcount does not become zero users. `integrations: null`
normalises to `UNKNOWN`; `integrations: []` normalises to `NONE_REPORTED` —
and only the second one is allowed to affect the classification.

### Two guardrails found by running the hostile fixture

- **Record conservation.** An out-of-vocabulary `group` or `function` maps to
  `UNKNOWN` while the value as given is preserved in `*_as_given`, and the row
  is listed in an "Entries not placed in the grid" table. `coverage()` +
  `unmapped()` is exhaustive and disjoint over the collection — a test asserts
  the two sum to the record count. A row that disappears from a coverage report
  is an invisible gap.
- **Quarantine, not just a flag.** A record carrying an individual identifier
  (`employee_id`, `netid`, …) is forced to `UNKNOWN` and held open until it is
  resubmitted keyed to a role. Flagging it while still counting it would mean
  the identifier was accepted into the baseline anyway. Normalisation copies
  known fields only, so the value never reaches the output — asserted, not
  assumed. This inventory assesses organizational capability and carries no
  field that rates a person.

### The interview instrument

`interview_guide.py` holds the question bank. Every question is tagged with
what it `seeks`; `self_rating`, `maturity_score`, `peer_comparison` and
`individual_performance` are in a banned set and a test walks every question to
enforce it. An answer nobody can verify is also an answer nobody can leave
blank honestly, which is how unsupported claims get manufactured.

Every question is explicitly answerable with "I don't know", and the recording
rule is printed on the instrument itself:

> If you do not know, say so and we write UNKNOWN. An UNKNOWN answer is a
> normal result and is reported as UNKNOWN — it is never estimated, and it is
> never recorded as zero or as 'no'.

`probes_for(entry)` returns the follow-up questions a thin record requires.
Probes fire from observed gaps, so a well-evidenced record is not over-probed —
a probe generator that fires on everything gets switched off.

---

## Run it

```sh
cd revenue/uiowa_rfq_18649_ai_use_inventory

# classify a collection and write CSV + JSON + Markdown
python3 inventory.py --input fixtures/synthetic_ai_use.json --outdir out

# read the report on stdout instead
python3 inventory.py --input fixtures/synthetic_ai_use.json --print

# the same instrument against deliberately damaged records
python3 inventory.py --input fixtures/synthetic_ai_use_hostile.json --print

# the interview guide, and the probes a collection requires
python3 interview_guide.py --guide
python3 interview_guide.py --probes fixtures/synthetic_ai_use.json

# tests
python3 -m unittest -v test_inventory
```

Measured on the 10-record synthetic collection:

```
records=10 active=2 informal=4 planned=2 unsupported=1 unknown=1 gaps=19
```

Three of those are demotions with a recorded reason. Coverage shows a real gap:
**testing is captured for ESS only** — the RIS and IAM testing cells read
`NO_ENTRY_CAPTURED`, meaning nobody was asked, which is not a finding of no AI
use.

---

## Files

| File | What it is |
| --- | --- |
| `schema.py` | field contract, vocabularies, validation, UNKNOWN normalisation |
| `inventory.py` | the classifier, coverage grid, gap report, CSV/JSON/Markdown renderers, CLI |
| `interview_guide.py` | the question bank and the probe generator |
| `fixtures/synthetic_ai_use.json` | 10 fictional entries: two strengths, one unsupported claim, three demotions, one status/evidence conflict |
| `fixtures/synthetic_ai_use_hostile.json` | 8 deliberately damaged records |
| `sample_output/` | committed output of the clean fixture; a test fails if it drifts from the code |
| `test_inventory.py` | 43 unittest cases |

## What is working vs. draft

**Working and tested.** The classifier, the UNKNOWN normalisation, the coverage
grid with record conservation, the gap report, the quarantine rule, all three
output formats, the CLI including its error paths, and the probe generator.

**Draft, pending real evidence.** Every record in `fixtures/` is fiction. The
bucket thresholds (what counts as a recurring cadence, whether an unintegrated
but evidenced use is an experiment) are reasonable defaults for rehearsal and
should be confirmed with the University before they classify a real interview.

## Scope

This lane produces an inventory. It does not score maturity, rank against peer
institutions, certify anything against a framework, evaluate an individual, or
recommend a product. `group` / `area` / `synthetic://` join keys and the
`proposed_evidence_id` column are shaped to fit the evidence register in
`../uiowa_rfq_18649_workshare/`; this lane emits those keys and does not write
into another lane's files.
