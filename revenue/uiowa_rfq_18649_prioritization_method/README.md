# UIOWA-029 — Recommendation prioritization and horizon method

Solicitation 18649. Work order UIOWA-029: *"Design a transparent method to
weigh quality, security and delivery impact against implementation complexity,
dependencies and adoption effort. Express uncertainty in effort ranges and
organize recommendations into the RFQ's 0–90, 90–180 and 180+ day horizons.
Deliverable: `29-prioritization-method.md` plus an editable synthetic
recommendation backlog."*

Built by seat `OP5-KELVIN` (Claude · Opus 5). Python 3 standard library only,
no network, no clock, deterministic.

## This lane contains no scoring model

Weighting quality, security and delivery against complexity is **already
implemented** in `../uiowa_rfq_18649_prioritization/` (UIOWA-084), with weight
profiles, a sensitivity sweep and its own `0`-versus-`UNKNOWN` rule. Building
a second one would give the engagement two methods that disagree, so this lane
binds to that one and adds the part it does not do: **organizing ranked
recommendations into horizons**. A test asserts no weights, profiles or
scoring function exist here.

## Two quantities kept apart

| | What it is | What it feeds |
| --- | --- | --- |
| `complexity` | UIOWA-084's 1–5 band — how hard, relative to other items | **ranking** |
| effort range | low/high days | **scheduling** |

A high-complexity item is not automatically a long one, and a cheap item is
not automatically a quick win. Substituting one for the other is how a
prioritized list turns into an undeliverable plan.

## The horizon rules

Seven rules, each with an id, each stated in the generated document and
checked by `--check`:

- **H1** — unsized work may not be proposed for 0–90. It becomes
  `NEEDS_ESTIMATE`, which is **not a horizon** and is reported separately so
  it cannot be mistaken for work scheduled late.
- **H2** — a prerequisite may not sit in a later horizon than its dependent.
- **H3** — a quick win is effort at or under the threshold, at least one
  assessed non-zero effect, and no prerequisites.
- **H4** — an item with prerequisites is proposed no earlier than its latest one.
- **H5** — an item at or above the high-effort threshold goes to 180+ unless
  declared otherwise **with a stated reason**.
- **H6** — effort is a range; a point estimate is permitted but flagged.
- **H7** — **a declared horizon is never overwritten.** The tool proposes and
  compares; a difference is reported for a person to settle.

Thresholds (`quick_win_max_effort_days = 10`, `high_effort_min_effort_days =
60`) are parameters, stated in `backlog.json`, not findings. A test changes one
and asserts items move.

## What the worked backlog produces

```
items=9 quick_wins=3 prerequisite_work=2 violations=0 disagreements=2
```

All three classes the order names are present: quick wins, prerequisite work
(items others depend on), and high-effort items. One item is unsized and is
held out of the horizons rather than guessed into one. Two items disagree with
their proposal — both carry a declared reason, and both are reported rather
than corrected:

- `REC-SYN-IAM-SEC-003` declared `0-90`, proposed `90-180` — placed early
  because two later items depend on it, with the team accepting the horizon is
  tight.
- `REC-SYN-RIS-SD-006` declared `90-180`, proposed `180+` — the team intends
  to split it, and the split is not yet written down, so the range still covers
  the whole piece of work.

A high-effort item pulled early **with** a reason is a disagreement. The same
move **without** a reason is a violation. `backlog_violations.json` exercises
all eight violation codes, and a test asserts every one of them fires.

## Run it

```sh
cd revenue/uiowa_rfq_18649_prioritization_method

python3 method.py --check        # exit 1 on any rule violation
python3 method.py --render       # regenerate 29-prioritization-method.md
python3 method.py --outdir out   # machine-readable horizons.json
python3 -m unittest -v test_method
```

## Files

| File | What it is |
| --- | --- |
| `29-prioritization-method.md` | **the named deliverable**, generated from the backlog |
| `backlog.json` | **the editable synthetic backlog** — 9 recommendations, thresholds at the top |
| `backlog_violations.json` | deliberately broken; exercises all eight violation codes |
| `method.py` | the horizon rules, proposal, comparison, renderer, CLI |
| `test_method.py` | 36 unittest cases |

## What is working vs. draft

**Working and tested.** All seven rules, all eight violation codes, the
proposal-versus-declaration comparison, the UNKNOWN and point-estimate
handling, parameter sensitivity, and the CLI.

**Draft.** The backlog is fiction. The thresholds are defaults for rehearsal.
Nothing here is checked against available capacity — an item can be proposed
for 0–90 that the organization has no room for, because capacity is not an
input to this lane.

## Still UNKNOWN

- the real recommendation set — this backlog is fiction
- whether a horizon means start or completion; the rules treat it as the
  window in which the work is done, and that is not confirmed
- the University's actual capacity per horizon, so nothing is checked against
  available effort
- which prerequisites the assessment team treats as binding rather than preferred
- whether the quick-win and high-effort thresholds are the right ones
