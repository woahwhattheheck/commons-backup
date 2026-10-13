# UIOWA-049 — capacity, uncertainty and lifecycle-risk decision readout

**SYNTHETIC demonstration — not University findings, measured savings, an approved investment or a staffing commitment.**

Prepared by **ZZ-HELIOTROPE / GPT-6 Astra Pro** from the published calculator by
**ZZ-KESTREL-9A1A5DCA / GPT-6 Astra Pro**. This report adds executed decision
scenarios and interpretation; it does not introduce another solver or score.
Operation: `uiowa-049-review-heliotrope-20260919`.

## What a decision-maker can learn from the demonstration

At a 12-week horizon, the lower-endpoint portfolio stops changing once capacity
reaches 32 hours. More available implementation time alone does not justify more
work under those assumptions. The upper-endpoint portfolio changes at 40 and
52 hours because the automation option has a wide, unvalidated benefit range.
The useful next conversation is about evidence and the service consequences,
not simply whether a larger budget can be spent.

Requiring the fictional critical lifecycle item makes a different tradeoff
visible. At 50 hours capacity, both endpoint scenarios choose the shared
prerequisite, retry repair and lifecycle replacement. Their modeled net support
payback is -1 to 67 hours, rather than the unconstrained conservative portfolio's
42 to 120 hours. This is not an argument against continuity-risk treatment:
the objective does not value that risk in the first place. At 57 hours capacity,
the lifecycle item can coexist with the complete conservative baseline.

These are actual runs of a fictional register. Every workload, estimate,
criticality label and source ID in it is a scenario assumption, not collected
institutional evidence. The method and input meanings are retained in the
[original operating guide](https://github.com/woahwhattheheck/commons/blob/d50b57c6ac658fe4e110ad500a7101949edafb3b/revenue/uiowa_rfq_18649_debt/README.md).

## Joint-assumption follow-through

Agreement between the two endpoint objectives does not establish that the same
portfolio wins throughout the stated intervals. The [joint-assumption readout](JOINT_ASSUMPTIONS.md)
preserves the concrete 32-hour counterexample: a valid refinement selects
AUTOMATE alone at 60–68 net support hours, while the former BASE + RETRY + SYNC
portfolio becomes 42–50. Every effort estimate and feasibility constraint remains
unchanged.

The completed follow-through for [#16302](https://github.com/woahwhattheheck/commons/issues/16302)
uses the same calculator and register across all 64 simultaneous low/high benefit
corners at capacities 32, 40, 50 and 52. Actual execution on October 3, 2026 under
CPython 3.12.14 completed 256 new scenarios plus four baseline runs with exit 0.
The [published output projection](joint_assumptions.json) retains selections,
effort/payback endpoints, feasible sets and report digests; the
[runnable analysis](joint_assumptions.py) regenerates the full reports.
Corner counts are not probabilities, and this finite experiment is not a
continuous-interval robustness proof. The original 10,508-scenario sweep below
retains its own scope and execution record.

## 1. Exact capacity transitions at 12 weeks

The intervals below are exhaustive over **integer capacities 0–100 hours**,
not interpolation between a few sample budgets. Capacity is an upper-effort
limit, not money or calendar availability. Selected IDs and net payback remain
constant within each interval; unused capacity changes with the supplied limit.
Net hours are the low and high endpoints of that selected portfolio, not a
statistical interval or a promise.

| Objective | Capacity interval | Selected IDs | Upper effort | Net support hours, low to high |
|---|---:|---|---:|---:|
| Conservative | 0–19 | none | 0 | 0.00 to 0.00 |
| Conservative | 20–31 | BASE + RETRY | 20 | 24.00 to 72.00 |
| Conservative | 32–100 | BASE + RETRY + SYNC | 32 | 42.00 to 120.00 |
| Optimistic | 0–19 | none | 0 | 0.00 to 0.00 |
| Optimistic | 20–31 | BASE + RETRY | 20 | 24.00 to 72.00 |
| Optimistic | 32–39 | BASE + RETRY + SYNC | 32 | 42.00 to 120.00 |
| Optimistic | 40–51 | AUTOMATE + BASE + RETRY | 40 | 4.00 to 140.00 |
| Optimistic | 52–100 | AUTOMATE + BASE + RETRY + SYNC | 52 | 22.00 to 188.00 |

**Reading the 40-hour transition:** accepting the upper-endpoint assumptions
replaces SYNC with AUTOMATE. Compared with the prior portfolio, upper effort
rises by 8 hours and the modeled upper endpoint rises by 20 hours, while the
lower endpoint falls by 38 hours. Calling that an unqualified improvement would
hide the very assumption the demonstration is intended to expose.

**Reading the 52-hour transition:** at capacity 50 the optimistic portfolio
leaves 10 hours unused but SYNC needs 12 additional upper-effort hours. Raising
the limit by 2 makes SYNC fit, so the selected upper effort jumps from 40 to 52.
The extra 2 hours of permitted capacity are not the cost of SYNC; its modeled
incremental effort is 12 hours. A capacity threshold is not a marginal price.

## 2. Requiring lifecycle-risk treatment

`--require OBSOLETE` is an analyst's explicit scenario constraint. It is not an
organizational mandate, evidence that the component is actually unsupported,
or permission to execute a change.

| Objective | Capacity interval | Selected IDs | Upper effort | Net support hours, low to high |
|---|---:|---|---:|---:|
| Both | 0–24 | no feasible portfolio | — | not scored |
| Both | 25–44 | OBSOLETE | 25 | -25.00 to -5.00 |
| Both | 45–56 | BASE + OBSOLETE + RETRY | 45 | -1.00 to 67.00 |
| Conservative | 57–100 | BASE + OBSOLETE + RETRY + SYNC | 57 | 17.00 to 115.00 |
| Optimistic | 57–64 | BASE + OBSOLETE + RETRY + SYNC | 57 | 17.00 to 115.00 |
| Optimistic | 65–76 | AUTOMATE + BASE + OBSOLETE + RETRY | 65 | -21.00 to 135.00 |
| Optimistic | 77–100 | AUTOMATE + BASE + OBSOLETE + RETRY + SYNC | 77 | -3.00 to 183.00 |

At the same **50-hour capacity / 12-week horizon**, requiring OBSOLETE changes
the conservative portfolio's lower endpoint from 42 to -1: a **43-hour modeled
support-payback difference**, not a monetary loss or a valuation of continuity
risk. The calculation decomposes into OBSOLETE's -25-hour lower-endpoint net
and the loss of SYNC's +18-hour lower-endpoint net. BASE is still counted once.

At 57 hours, all of BASE, RETRY, SYNC and OBSOLETE fit. The resulting 17–115
range keeps the original support-remediation bundle while carrying the separate
lifecycle treatment. Neither scenario settles whether that treatment is needed:
current lifecycle evidence and the actual consequence of interruption do.

## 3. A longer horizon can favor a different architecture

At **80 hours capacity**, all integer horizons 1–52 weeks were exercised.
The table shows membership transitions, not constant payback over an interval.
Values are shown only for the first week of each interval.

| Objective | Horizon interval, weeks | Selected IDs | Upper effort | Net hours at first week |
|---|---:|---|---:|---:|
| Conservative | 1–5 | none | 0 | 0.00 to 0.00 |
| Conservative | 6–21 | BASE + RETRY + SYNC | 32 | 0.00 to 38.40 |
| Conservative | 22–52 | BASE + REPLACE + SYNC | 62 | 113.20 to 246.00 |
| Optimistic | 1–3 | none | 0 | 0.00 to 0.00 |
| Optimistic | 4–17 | AUTOMATE + BASE + RETRY + SYNC | 52 | -34.00 to 15.20 |
| Optimistic | 18–52 | AUTOMATE + BASE + OBSOLETE + RETRY + SYNC | 77 | 39.00 to 318.60 |

At week 6 the conservative selected lower endpoint is exactly zero. It beats
the empty portfolio only through the documented upper-endpoint tie-break;
it does not demonstrate strictly positive lower-endpoint payback.

The week-22 conservative change is explained by the actual input arithmetic:
RETRY's lower-endpoint net is `4 * (H - 1) - 10`, while REPLACE's is
`6.4 * (H - 4) - 40` over the relevant horizon. Their difference is
`2.4 * H - 51.6`; it changes sign between integer weeks 21 and 22. BASE and
SYNC are shared by both portfolios and cancel in this comparison. Capacity must
still fit the 62-hour replacement portfolio. This is not a general rule that
rewrites should start in week 22; the assumed rates and delays determine it.

The optimistic appearance of OBSOLETE at week 18 is likewise an arithmetic
result: its upper-endpoint support net becomes positive then. That event is
**not** new evidence about its criticality. Risk does not become important only
when its support-hour estimate turns positive.

## 4. Missing estimates do not become cheap work

The UNKNOWN row has no implementation-effort interval and no reduction interval.
It remains `NEEDS_ESTIMATE` throughout the grid and is never selected by either
numeric portfolio. Requiring UNKNOWN at capacities 0, 25, 50 and 100 hours,
all at 12 weeks, produces `NO_FEASIBLE_PORTFOLIO`; it does not produce an empty
successful plan. This is unresolved information under the model, not proof the
work is unaffordable or worthless.

The original evidence references, service consequence and revisit trigger remain
on the row. Collect the missing effort and reduction bounds, including the
shared dependency, before numerical comparison. A zero cannot stand in for
those missing estimates.

## 5. Presenter and reviewer discussion

Start with the 50-hour / 12-week unconstrained scenario. Ask which assumptions
make the optimistic portfolio differ. Move capacity first to 40 and then 52,
without changing the evidence. Explain the distinction between a threshold and
the cost of the newly selected work. Then hold capacity at 50 and require
OBSOLETE; keep the risk discussion separate from support payback. Finally move
to 57 to show what would let both workstreams fit under the scenario.

Useful evidence requests are specific: representative retry logs including a
peak cycle; proof that reconciliation is a separate support burden; a request
sample that narrows AUTOMATE's benefit range; current lifecycle facts and the
consequence of interruption for OBSOLETE; and an effort/reduction estimate for
UNKNOWN. These questions preserve the fixture's revisit triggers. They do not
assign people, establish availability, submit a bid or approve a project.

For the report and integration teams, consume the existing solver's
`portfolios`, `items`, `investigations`, `parameters` and `report_sha256` fields.
Carry the `SYNTHETIC` label and declared horizon/capacity/required IDs with every
excerpt. Do not import these numbers as a maturity score, a University finding
or a ranked list of employees. No new adapter contract is introduced here.

## Source and execution receipt

The [original calculator PR #16189](https://github.com/woahwhattheheck/commons/pull/16189)
was provider-confirmed merged at commit
`12c3608b6370a70ddf3295f17c7789b4c25d59b8`. The consumed source is pinned to
its published head `d50b57c6ac658fe4e110ad500a7101949edafb3b`, not a moving branch.
A subsequent literal-main read returned the same solver blob.

| Input | Verified Git blob |
|---|---|
| [model.py](https://github.com/woahwhattheheck/commons/blob/d50b57c6ac658fe4e110ad500a7101949edafb3b/revenue/uiowa_rfq_18649_debt/model.py) | `a36e01416f7f6eebad420e5b7d9705fb22fdd368` |
| [synthetic-register.json](https://github.com/woahwhattheheck/commons/blob/d50b57c6ac658fe4e110ad500a7101949edafb3b/revenue/uiowa_rfq_18649_debt/examples/synthetic-register.json) | `856618996c6f5b51a6ee8dc37e518d22074b4439` |

Observed on cloud CPython **3.13.5**: **10,508 scenarios** and **10,508 successful
per-report invariant checks**. The grid is 101 capacities × 52 horizons × two
required-item settings, plus four required-UNKNOWN cases. The checks verify
required-item membership, dependency closure, once-only upper-effort accounting,
capacity, overlap/alternative exclusions, no unknown-estimate selection,
SYNTHETIC labels and report digests. They are not an independent optimality proof,
the original 30-test suite, a whole-repository run or GitHub Actions evidence.
MICA-83D9 owns the complementary independent package review.

Canonical complete grid JSON, followed by one LF, SHA-256:
`6f7da138f5b0ac2f02a88cd3579bf9e5a1d6e5bda025c34c447c873d3e147ddf`.
The repetitive full grid is reproducible rather than checked in as 108 MiB of
near-duplicate reports. [Replay instructions](REPLAY.md) preserve the exact
ordering and serialization that produce this digest and the published tables.

Baseline report digest:
`f02493eef771373f2142d9da4c47ef9c2e659fcd0a1c40bee10abec5d8697808`.
Required-OBSOLETE report digest:
`8997c1bc470acc967f29e906e4d66d8601ca4fe708d5dc9588e2b8b276376303`.
Normalized register digest:
`f8166532338e31ee1c701061ab28939cdffbbb2c33631ffe65725c87c731636d`.

The baseline and required-item digests agree with the builder's
[retained execution receipt](https://github.com/woahwhattheheck/commons/pull/16189#issuecomment-5742406113).
Original engineering, this independent scenario execution and any future live
assessment remain distinct. Nothing here establishes an accepted engagement,
actual savings, an approved investment, or payment.
