# Dependency-aware phased roadmap planning

UIOWA-085 / #16127. An offline planning kit that turns draft recommendations into
0–90, 90–180 and 180+ relative calendar-day start horizons. It retains original
recommendation IDs, finding and evidence references, owner roles, practice
changes, observable outcomes and assumptions. Python 3.10+ and the standard
library are sufficient.

The supplied source and worked outputs are **entirely synthetic**. They are not
University findings, approved recommendations, staffing assignments or booked
calendar events. This program makes no network calls and performs no scheduling,
procurement, account or deployment actions.

## Run and edit

From this directory, choose a new output directory:

```sh
python3 roadmap.py synthetic_recommendations.json /tmp/roadmap-original
python3 roadmap.py /tmp/roadmap-original/planning_table.csv /tmp/roadmap-revised
```

The checked-in [example/roadmap.html](example/roadmap.html) is an immediately
usable view. Open it in a browser, use the keyboard-focusable table region on a
narrow display, and expand an item's sources and assumptions. No JavaScript,
fonts or assets are fetched. Markdown and JSON retain the same underlying data.
The [editable planning table](example/planning_table.csv) can be copied into a
spreadsheet or text editor and imported again with the second command.

Each new output directory contains:

| File | Use |
| --- | --- |
| `planning_table.csv` | Editable input columns plus recomputed planning columns |
| `roadmap.json` | Deterministic complete plan, source fields, issues and summary |
| `roadmap.md` | Readable table, outcomes, evidence and assumptions |
| `roadmap.html` | Self-contained horizon view with item details |
| `manifest.json` | Exact output hashes, written after the other four outputs |

Existing destinations are never overwritten. If writing is interrupted, a
missing final manifest identifies an incomplete directory; no prior output is
deleted. Ordinary valid reports exit 0, invalid input or filesystem operations
exit 2. Add `--require-plannable` to write a valid report but exit 3 when any
item remains unscheduled or has a start-phase risk/conflict. This describes
model feasibility, not approval to do work.

### Combine dependency structure with an edited planning table

The separate dependency oracle consumes the original JSON source contract. The
planner can pass its parsed JSON or edited CSV to that unchanged component in
the same invocation:

```sh
python3 roadmap.py example/planning_table.csv /tmp/roadmap-combined \
  --include-dependencies
```

This adds `dependencies.json`, `dependencies.md` and `dependencies.dot` to the
new directory and its manifest. The HTML links to all three. DOT is portable
graph source; rendering it is optional and the command installs no software.
Both component paths, source SHA-256 identities and their input digests are
recorded in `manifest.json`. The oracle's full-input digest and the planner's
input digest describe the same parsed source; its graph-projection digest is
separate. Exact recommendation IDs remain the join key.

Graph and duration outcomes remain distinct. On the supplied edited-table
source, the graph is `CONSISTENT` with zero errors/warnings while the duration
plan still contains two unscheduled items, one phase risk and one phase conflict.
The option does not turn graph consistency into schedule feasibility. With
`--require-plannable`, either incomplete planning or a non-consistent graph
produces exit 3 after writing the usable reports. Ordinary combined reports
exit 0. Invalid inputs accepted by one component but rejected by the other
produce exit 2 before the output directory is created.

The option requires the sibling
`uiowa_rfq_18649_roadmap_dependency_oracle/checker.py` already present in this
repository. A standalone copy of this directory still supports ordinary
planning; it reports a clear error if the optional oracle is unavailable.

## Source contract

A JSON document has exactly `schema_version` (integer 1), `title`, `synthetic`
(boolean), `assumptions` (text array) and nonempty `recommendations`. Each row
has these fields:

| Field | Meaning |
| --- | --- |
| `id`, `title` | Stable recommendation identity and description |
| `group` | ESS, RIS, IAM or DEPARTMENT |
| `phase` | `0-90`, `90-180` or `180+` requested start horizon |
| `owner_role` | Proposed role, or `null` when unknown |
| `depends_on` | Exact prerequisite recommendation IDs |
| `duration_days` | `[optimistic, pessimistic]` nonnegative integer calendar days, or `null` |
| `finding_refs`, `evidence_refs` | Original source reference arrays |
| `practice_change`, `observable_outcome` | Proposed change and evidence needed to judge its outcome |
| `assumptions` | Explicit assumptions behind this item |

Duration is elapsed calendar time, not person-days, working days, probabilities
or a confidence interval. Zero-duration milestones differ from missing estimates.
Group and role fields are planning context, not evidence that real personnel
have accepted work. Empty supporting references and unknown owners remain
visible issues.

The CSV repeats `document_title`, `synthetic` and JSON-encoded
`document_assumptions` on every row; these must agree. Arrays are JSON inside
CSV cells. Blank duration means unknown. `planning_state`, dates, `layer`,
`status`, `phase_state` and `issues` are derived: import ignores their edited
values and recomputes them. Formula-like leading text is apostrophe-prefixed on
export and reversibly decoded on import. Preserve cell text and UTF-8 when
round-tripping through spreadsheet software; no formulas or macros are supplied.

Duplicate IDs/JSON keys, unsupported fields, invalid phases/groups, reversed or
negative durations and Boolean duration values produce clear input errors.
The supplied [synthetic_recommendations.json](synthetic_recommendations.json)
is the complete editable input example; `validate()` is the executable contract.

## Calculation and unresolved work

Horizon boundaries are half-open: day 90 belongs to the second phase, day 180
to the third. For an item with known duration and resolved prerequisites:

```text
start_min  = max(requested phase start, each prerequisite finish_min)
start_max  = max(requested phase start, each prerequisite finish_max)
finish_min = start_min + duration_min
finish_max = start_max + duration_max
```

`ON_PHASE` means both start bounds fit the requested horizon. `AT_RISK` means
only the optimistic bound fits. `OUTSIDE_PHASE` means even the optimistic bound
misses it. Later finishes are marked separately; the planner does not silently
change requested phases. HTML shows possible work envelopes, not committed
occupation of the entire interval.

Missing prerequisites and durations retain null dates. Their dependents remain
unscheduled. A cycle and its blocked descendants receive
`CYCLE_OR_BLOCKED_BY_CYCLE`; this deliberately does not label every descendant
as a cycle member. Other connected components still produce useful plans.
Dependency layers identify independent branches, not available staff capacity.
The algorithm sorts IDs and traverses iteratively.

## Worked source and composition

The published 12-item input produces 10 planned items, two unscheduled items,
one phase risk and one phase conflict. R08's duration and owner are unknown;
R09 depends on it and stays unscheduled. R11 starts at D80–D110, crossing its
requested phase boundary. R12 cannot start before D105, so its first-phase
request is infeasible. R06 combines both pilot paths at D90 and finishes at
D130–D150; R07 starts at D180.

For an operator revision, copy the planning CSV, enter an explicitly hypothetical
R08 duration/role and rerun into a new directory. Its dependent then becomes
calculable. Keep the revised assumption explicit; a computable date does not
prove the assumption. Evidence locators in the supplied example resolve into
[synthetic_evidence.md](synthetic_evidence.md).

This restores the original planner from the retained
`swarm-zz/uiowa-085-quartzfin47-roadmap` source for operation
`uiowa-085-quartzfin47-20260919`. Original planner/input author: ZZ-QUARTZFIN-47.
The recovered Python source blob was
`4870639c2cb077657feeba3a4e9dae739df5acfe`. Recovery completes HTML access to all
item sources/assumptions, adds keyboard-scrollable narrow-screen tables, and
ships outputs produced by the actual CLI. The donor branch remains intact.

The separate [dependency oracle](../uiowa_rfq_18649_roadmap_dependency_oracle/)
checks graph structure and supplies an existing compatible six-item example.
It does not replace duration propagation here. Running its
`examples/roadmap085.json` through this planner yields two planned and four
unscheduled items because one shared prerequisite has unknown duration, even
though the graph itself has no contradiction.

Existing prioritization and resource-estimation components retain their own
authority: preserve recommendation IDs and ranking rationale, compare staff
capacity separately, and use `plan(document)` or JSON output for integration.
This planner does not calculate a maturity score, authenticate evidence or
promise a one-to-two-level progression. Its input digest is reproducibility
metadata; it is not an evidence-authority root.
