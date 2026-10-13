# UIOWA-107 — Research-deadline continuity demonstration

Solicitation 18649. Work order UIOWA-107: *"Create a fictional
research-administration reporting deadline affected by a shared identity
service and a scheduled application change … Dependency and capacity
assumptions are explicit; results identify practical preparation choices and
the evidence needed to distinguish them."*

Built by seat `OP5-KELVIN` (Claude · Opus 5). Python 3 standard library only,
no network at runtime, deterministic.

---

## Everything here is fictional

The deadline, the shared identity service, the scheduled application change
and every number in `fixtures/` were invented for rehearsal. **This is not a
University of Iowa finding**, not a statement about University capacity, and
**not a commitment to any date** — the deadline is expressed relative to
kickoff, never as a calendar appointment. The payload carries
`authority: FICTIONAL_REHEARSAL_ONLY` and the same `prohibited_interpretation`
shape as the collection landed for UIOWA-091.

Still **UNKNOWN**, listed as evidence to collect later:

- the real research-administration reporting calendar and its true cutoff
- whether the shared identity service publishes a change-freeze window at all
- who is empowered to defer a scheduled application change, and on what notice
- actual analyst capacity in the window, as opposed to roster headcount
- whether temporary capacity is fundable at all in that period

---

## The design choice this order turns on

The tempting build is: compute an exposure number per option, print the
winner. That is false certainty dressed as analysis — and on this scenario it
would be badly wrong, because the input the whole question rests on (**how
long the shared identity service's change freeze holds things up**) has never
been asked for.

So the tool is built to refuse a conclusion it cannot support.

**Every quantity is an interval with a BASIS.** `MEASURED` (somebody can point
at the record — a `source_ref` is required, or the validator rejects it),
`ESTIMATED` (a practitioner's range, not a measurement), `ASSUMED` (a working
figure with nothing behind it), `UNKNOWN`.

**An UNKNOWN assumption carries no numbers at all.** Supplying a value under an
`UNKNOWN` label is rejected outright — that is an invented figure wearing a
disclaimer. It propagates as `0 – UNBOUNDED`, and any conclusion resting on it
comes out `NOT_DETERMINED`. No default, no midpoint, no zero.

**Verdicts are three states, not a score.** `FITS` (worst case still inside
capacity) · `AT_RISK` (best case already exceeds capacity) · `NOT_DETERMINED`
(ranges overlap, or a bound is missing — and the blocking input is named).

**Options are compared only when the comparison holds across the whole range.**
One option is reported lower than another only if its interval *ends before*
the other's *begins*. Otherwise the pair is `NOT_SEPARABLE` and says so.

**Then it does the useful thing.** For every unseparated pair it runs a
sensitivity walk — pinning each assumption to each end of its range — and
reports which assumption, if resolved, would separate them. That becomes a
concrete evidence request. When an input cannot be pinned at all (the UNKNOWN
upper bound) the request is *"obtain any upper bound for this."* When no single
assumption would separate the pair, it says that too, rather than
manufacturing a preference from the numbers.

**There is no `recommended` field anywhere in the output**, by design — a test
greps the payload for `recommend`, `winner`, `best option`, `maturity`,
`score` and `percentile` and fails if any appears. The tool narrows the
question and names what to go find out; a person decides.

---

## What the worked scenario actually produces

```
options=4 undetermined=3 pairs=6 unseparated=3 unresolved_assumptions=1
```

| Option | In-window exposure | Capacity | Verdict |
| --- | --- | --- | --- |
| **OPT-A** proceed as scheduled | 20–UNBOUNDED | 32–40 | `NOT_DETERMINED` |
| **OPT-B** defer past the deadline | 2–2 | 32–40 | `FITS` |
| **OPT-C** proceed, rehearsed rollback | 16–UNBOUNDED | 32–40 | `NOT_DETERMINED` |
| **OPT-D** proceed, add temporary capacity | 20–UNBOUNDED | 32–56 | `NOT_DETERMINED` |

Three of the four are undetermined, and all three for the **same single
reason**: `ASM-002`, the identity-service change-freeze wait, has no upper
bound because nobody has asked IAM for one. That is the finding. The honest
output of this analysis is *"you cannot choose between A, C and D yet — and
here is the one question that would let you."*

Two results are worth pointing at:

- **A conclusion that survives the unknown is still reported.** OPT-B's
  exposure (2–2) ends before every other option's begins, so *deferring is
  lower in-window exposure no matter what the identity freeze turns out to
  be*. Refusing to say that would be over-caution, not honesty. It is labelled
  as a statement about in-window hours — **not** a recommendation, and it does
  not price what OPT-B's `not_modelled` list names.
- **OPT-A and OPT-D have identical exposure and differ only in capacity.**
  Comparing exposure alone would report "not separable" and say nothing
  useful. The tool detects the capacity difference and names it: the whole
  distinction is `ASM-006`, temporary capacity, which is `ASSUMED 0–16` with
  nobody having confirmed funding. That is a much better question than a
  number.

---

## Run it

```sh
cd revenue/uiowa_rfq_18649_deadline_continuity

python3 continuity.py --input fixtures/ris_deadline_scenario.json --outdir out
python3 continuity.py --input fixtures/ris_deadline_scenario.json --print
python3 -m unittest -v test_continuity
```

## Files

| File | What it is |
| --- | --- |
| `intervals.py` | `Assumption` (basis + validation) and `Interval` (unbounded-aware arithmetic) |
| `continuity.py` | options, verdicts, separability, the sensitivity walk, renderers, CLI |
| `fixtures/ris_deadline_scenario.json` | the fictional RIS scenario — 7 assumptions, 4 options, 2 dependencies |
| `sample_output/` | committed output; a test fails if it drifts from the code |
| `test_continuity.py` | 42 unittest cases |

## What is working vs. draft

**Working and tested.** Interval arithmetic including the unbounded cases,
assumption validation (all four bases and their refusals), the three verdicts,
pairwise separability, the sensitivity walk and its evidence requests, the
capacity-difference detection, determinism, all four output files, and the CLI
error paths.

**Draft, pending real evidence.** The scenario is fiction. The exposure model
is deliberately simple — it sums in-window hours and compares them to in-window
capacity. It does **not** model probability of failure, and it does not price
anything in an option's `not_modelled` list. Both are stated per option rather
than hidden.

## Scope

This tool compares **preparation options**. It does not rank teams, units or
people, does not score maturity, certifies nothing, runs no load test, reads no
live system, and schedules nothing — availability is a stated scenario
assumption, never an appointment. Join keys (`service` ∈ ESS/RIS/IAM,
`synthetic: true`, `synthetic://` locators) match the collection landed for
UIOWA-091; this lane emits those keys and writes into no other lane's files.
