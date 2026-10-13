# 29 — Recommendation prioritization and horizon method

Solicitation 18649, work order UIOWA-029.

**The synthetic backlog below is fictional.** It is not a University of Iowa
finding and the horizons are not a commitment to any date.

## What this method does not contain

It contains **no scoring model**. Weighting quality, security and delivery
against complexity is implemented in `../uiowa_rfq_18649_prioritization/`
(UIOWA-084), with weight profiles, a sensitivity sweep and its own `0`-versus-
`UNKNOWN` rule. A second scoring model would give this engagement two methods
that disagree. This method binds to that one and adds horizon organization,
which it does not do.

## Two quantities that must not be conflated

| | What it is | What it feeds |
| --- | --- | --- |
| `complexity` | UIOWA-084's 1–5 band: how hard, relative to other items | **ranking** |
| effort range | low/high days | **scheduling** |

A high-complexity item is not automatically a long one, and a cheap item is
not automatically a quick win. Substituting one for the other is the most
common way a prioritized list turns into an undeliverable plan.

## The horizon rules

| Rule | Statement |
| --- | --- |
| **H1** | An item whose effort is UNKNOWN may not be proposed for 0-90. A window cannot be committed to work nobody has sized. It is proposed as NEEDS_ESTIMATE, which is not a horizon. |
| **H2** | A prerequisite may not sit in a later horizon than the item that needs it. |
| **H3** | A quick win is an item with effort at or under the quick-win threshold, at least one assessed non-zero effect, and no prerequisites. It is proposed for 0-90. |
| **H4** | An item with prerequisites is proposed no earlier than the horizon of its latest prerequisite. |
| **H5** | An item whose lower effort bound reaches the high-effort threshold is proposed for 180+ unless the backlog declares otherwise with a stated reason. |
| **H6** | Effort is a range. A point estimate is permitted but is flagged, because a single number states a certainty the estimator may not have. |
| **H7** | A declared horizon is never overwritten. Where the proposal and the declaration differ, both are shown and the difference is reported. |

Parameters, stated rather than buried: `high_effort_min_effort_days = 60`, `quick_win_max_effort_days = 10`.
Change them in `backlog.json` and re-run.

## The worked backlog

| ID | Effort (d) | Complexity | Prereqs | Declared | Proposed | Agrees |
| --- | --- | ---: | --- | --- | --- | --- |
| `REC-SYN-ESS-SD-001` | 3–6 | 2 | — | 0-90 | 0-90 | yes |
| `REC-SYN-ESS-DEP-002` | 4–8 | 2 | — | 0-90 | 0-90 | yes |
| `REC-SYN-IAM-SEC-003` | 15–30 | 3 | — | 0-90 | 90-180 | **no** |
| `REC-SYN-ESS-SD-004` | 20–40 | 3 | REC-SYN-ESS-SD-001 | 90-180 | 90-180 | yes |
| `REC-SYN-RIS-DEP-005` | 60–110 | 5 | — | 180+ | 180+ | yes |
| `REC-SYN-RIS-SD-006` | 70–120 | 4 | — | 90-180 | 180+ | **no** |
| `REC-SYN-IAM-SEC-007` | 8–8 | 2 | — | 0-90 | 0-90 | yes |
| `REC-SYN-ESS-AI-008` | UNKNOWN | None | — | UNKNOWN | NEEDS_ESTIMATE | yes |
| `REC-SYN-IAM-DEP-009` | 30–50 | 4 | REC-SYN-IAM-SEC-003 | 90-180 | 90-180 | yes |

### Organized by declared horizon

- **0-90** — `REC-SYN-ESS-SD-001`, `REC-SYN-ESS-DEP-002`, `REC-SYN-IAM-SEC-003`, `REC-SYN-IAM-SEC-007`
- **90-180** — `REC-SYN-ESS-SD-004`, `REC-SYN-RIS-SD-006`, `REC-SYN-IAM-DEP-009`
- **180+** — `REC-SYN-RIS-DEP-005`
- **NEEDS_ESTIMATE** — `REC-SYN-ESS-AI-008`
- **UNASSIGNED** — none
- **INVALID_HORIZON** — none

`NEEDS_ESTIMATE` is not a horizon. It is where an item sits when nobody has
sized it, and it is reported separately so it cannot be mistaken for work
scheduled late. A partial range retains its supplied bound but still needs an estimate.
`UNASSIGNED` means sized work with no declared horizon; `INVALID_HORIZON`
means the declaration is outside the vocabulary. Neither means an unknown estimate.
Proposals inspect declared prerequisite horizons only, not other proposals.
They are per-item suggestions, not a jointly feasible transitive schedule.

### The three classes the order asks for

- **Quick wins** (3): `REC-SYN-ESS-SD-001`, `REC-SYN-ESS-DEP-002`, `REC-SYN-IAM-SEC-007`
- **Prerequisite work** (2, items other recommendations depend on): `REC-SYN-ESS-SD-001`, `REC-SYN-IAM-SEC-003`
- **High effort** (2): `REC-SYN-RIS-DEP-005`, `REC-SYN-RIS-SD-006`

## Where the proposal and the declaration differ

Rule H7: the declared horizon is never overwritten. Both readings are shown
and a person settles it.

**`REC-SYN-IAM-SEC-003`** — declared `0-90`, proposed `90-180`

- H3 not met: neither a quick win nor high effort
- Declared reason: Placed early because two later items depend on the inventory existing; the team accepts the horizon is tight.

**`REC-SYN-RIS-SD-006`** — declared `90-180`, proposed `180+`

- H5: lower effort bound 70 reaches the high-effort threshold 60
- Declared reason: The team wants it before the next reporting cycle and intends to split it; the split is not yet written down, so the effort range still covers the whole piece of work.

## Uncertainty

Effort is a **range**, and an item nobody has sized carries no range at all
rather than a placeholder. A point estimate is permitted but flagged, because
a single number states a certainty the estimator may not have. An effect that
was not assessed is `UNKNOWN` and does not contribute — it is not a zero.

## Still UNKNOWN

- the real recommendation set — this backlog is fiction
- whether a horizon means start or completion; the rules above treat it as the window in which the work is done, and that has not been confirmed
- the University's actual capacity per horizon, so nothing here is checked against available effort
- which prerequisites the assessment team treats as binding rather than preferred
- whether the quick-win and high-effort thresholds are the right ones; they are parameters of this method, not findings
