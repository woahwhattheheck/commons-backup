# Costed work-batch calculator

Select a worthwhile batch, rather than treating a tiny advertised reward as a
reason to spend an entire work session. This dependency-free Python 3.10+
calculator accounts for shared setup, direct costs, effort/inference cost,
explicit collection assumptions, a minimum net threshold, and UTC deadlines.
It returns a feasible sequential schedule and a valid optimization bound.

**WHAT-IF ONLY.** This is not a revenue forecast, source authenticator, task
claim, live deadline service, or replacement work queue. Keep using existing
operation IDs, `command.html`, `state/claims`, and the appropriate specialist
Slack channel. The existing `revenue/pursuit_portfolio` remains the distinct
priority/authority planner; this tool does not modify or bypass it. Before any
actual work or outreach, independently verify current terms, ownership,
deadlines, and payout mechanics; external outreach still needs Muse selection
and fresh provider-history checks. No provider calls or writes exist here.

## Run

From the repository root:

```sh
python -m tools.costed_work_batch plan tools/costed_work_batch/example.synthetic.json --format text
python -m tools.costed_work_batch plan tools/costed_work_batch/example.synthetic.json > /tmp/costed-batch.json
python -m tools.costed_work_batch verify tools/costed_work_batch/example.synthetic.json /tmp/costed-batch.json
python -m unittest tools.costed_work_batch.test_planner -v
python -O -m unittest tools.costed_work_batch.test_planner -v
python -m tools.costed_work_batch.benchmark
```

`-` reads a single JSON document from stdin. Results go to stdout; errors go to
stderr with exit code 2 and no partial result. `verify` recomputes the entire
result from the separately supplied scenario. Its `matches: true` proves
replay consistency, **not truth or authorization of the supplied scenario**.
Both inputs cannot use stdin simultaneously. Shell redirection is the caller's
responsibility, including preventing accidental overwrites.

## Input contract

The checked-in example is complete. All keys are required, unknown keys are
rejected, integers cannot be booleans/floats, IDs are bounded ASCII, and all
UTC timestamps have exact whole-second `YYYY-MM-DDTHH:MM:SSZ` form. Jobs and
families normalize by ID, making input order irrelevant.

A scenario contains `schema: costed-work-batch/v1`, `scenario_id`, `currency`,
`start_at`, `horizon_minutes`, `cash_budget_minor`,
`effort_cost_minor_per_minute`, `minimum_net_minor`, `node_budget`, `families`,
and `jobs`.

Each family contains an `id`, nonnegative `setup_minutes`, and nonnegative
`setup_cash_minor`. Each job contains:

- `operation_id` and `family_id`: existing canonical work identity and setup
  family. Duplicate operation IDs are rejected. Different aliases for one real
  obligation cannot be detected from these fields: reconcile those upstream.
- `availability`: `AVAILABLE`, `OWNED_ELSEWHERE`, or `UNAVAILABLE`, as explicitly
  supplied, **not checked against the actual claim ledger**.
- `work_units`, `minutes`, `cash_cost_minor`, `reward_minor`: one indivisible job
  or batch. Duration, cost, and reward are **totals for the entire job**;
  `work_units` is descriptive and does not multiply them. Split a divisible
  batch into disjoint canonical jobs only when that matches its actual terms.
- `collection_probability_bp`: explicit scenario assumption, 0 through 10000
  basis points. Never estimated from an advertised reward or a sender's claim.
- `valuation_basis`: `OWNER_SCENARIO`, `ADVERTISED_TERMS`, `ACCEPTED_TERMS`, or
  `UNVALUED`. These are caller labels, not authenticated contract states.
  `UNVALUED` requires both reward and probability to be `null` and is excluded.
- `evidence_ref`: bounded opaque reference, not a fetched or authenticated
  document. Keep actual contact details and credentials out of scenario IDs.
- `deadline_at`: exact UTC or `null` for the scenario horizon. Completion exactly
  on the deadline is permitted; both deadline and horizon must be met.

All money uses **one common unit and one minor-unit scale supplied by the
operator**. The currency label performs no conversion or scale inference. Do
not mix dollars and RTC, invent a token/USD exchange rate, or treat an unknown
payout as zero-cost money. Tax, FX, payment timing, refunds, and financing are
not modeled. The cash budget limits all direct and setup outlays without
assuming future reward receipts finance them. The effort cost is subtracted
from the objective but is not charged again against the direct-cash budget;
include an actual cash inference fee as direct cost without double counting it
in the effort rate.

## Economic objective

For each selected job, scenario value is
`floor(reward_minor * collection_probability_bp / 10000)`.

Batch net is the sum of these values, minus all selected job direct costs,
minus each used family's setup cost once, minus the explicit effort rate
multiplied by all job and setup minutes. Rounding is conservative per job.
Linearity of this scenario expectation does not establish probabilities,
independence, risk tolerance, or guaranteed collection.

The deterministic objective is maximum net, then minimum elapsed minutes,
then minimum direct cash, then the lexicographically smallest sorted operation
ID tuple. The empty batch with zero net is always available. A positive
`minimum_net_minor` is required; a batch below it does not become qualifying
because some work was technically possible.

Already-owned/unavailable jobs, unvalued jobs, individually impossible
cash/deadline jobs, and nonpositive marginal-net jobs remain in the report with
reason codes. Removing a nonpositive marginal job cannot worsen this model:
there are no dependencies, setup costs are nonnegative, and positive job time
is saved. A job unprofitable *after its standalone setup* is not removed when
its pre-setup marginal contribution is positive; several such jobs can justify
one shared setup together.

## Exact scheduling model and proof scope

One sequential crew starts at `start_at`; all jobs are available immediately.
Each family requires one fixed setup, performed before its first selected job.
Setup persists for the entire horizon; returning to the family incurs no
switching/setup penalty. Jobs are nonpreemptive and have positive whole-minute
durations. There are no release dates, dependencies, parallel workers,
calendar outages, sequence-dependent setups, or conditional rewards.

Under precisely this model, sorting selected jobs by earliest effective
deadline (then operation ID) is feasibility-complete. For any deadline `d`,
every selected job due by `d` and the setup for every family used by those jobs
must have completed by `d` in **any** feasible schedule. The earliest-deadline
prefix consumes exactly that necessary work and setup, and no later-deadline
job. Therefore its prefix cannot miss `d` when another schedule succeeds.
Nonnegative cash costs also mean a within-budget total has within-budget
prefixes. This argument does not extend to the excluded features above.

## Search and certificates

The iterative branch-and-bound enumerates include/skip decisions in that
feasibility-complete order. Deterministic greedy and whole-family heuristics
supply initial feasible incumbents, never an optimality claim.

For each remaining suffix, two fractional-knapsack relaxations bound its
positive marginal contributions: one keeps only remaining work time, the
other only remaining direct cash. Both ignore future setup costs/time and
deadlines, so both overestimate achievable additional net; their minimum is
still an upper bound. Exact integer ratio comparisons and upward rounding
avoid floating-point underestimates. Zero-cash jobs are included correctly.
Every unexplored subtree keeps its bound when the node budget is exhausted.

`search.lower_bound_minor` is the feasible incumbent net;
`upper_bound_minor` is the largest retained bound or incumbent. `OPTIMAL`
requires a completely exhausted/pruned search, including deterministic ties.
`BOUNDED` means search remains. A zero net gap may prove the net optimum while
tie resolution remains unfinished; `net_optimum_proven` says only that.

`QUALIFYING_SCENARIO_BATCH` means the feasible incumbent clears the supplied
threshold, not that it is necessarily optimal. `NO_QUALIFYING_BATCH` means the
model upper bound is below threshold (or the completed optimum is).
`SEARCH_INCOMPLETE` means no qualifying incumbent was found yet but the bound
still permits one. Unselected candidate jobs are never labeled unprofitable
merely because a bounded search omitted them.

Limits: 256 jobs/families, 1..1000000 expanded nodes, at most 525600 minutes,
up to 10^12 minor units per monetary input, and 1 MiB per CLI document. JSON
nesting above 32 is rejected before recursive parsing; duplicate keys and
nonfinite literal numbers are rejected. Input caps and a deterministic node
budget are **not a wall-time or memory SLA**. Suffix precomputation is quadratic
in the job cap. For large ambiguous instances, increase the node budget or
reduce the independently defined planning scope; never call a gap closed by
hiding omitted jobs. The CLI reads regular files through one descriptor,
checks metadata before/after reading, and refuses final symlinks where
`O_NOFOLLOW` exists. It does not claim protection against arbitrary hostile
same-process code, hostile writable ancestor trees, or file-writer races that
restore every observed metadata field.

## Worked example: synthetic, not earned money

The example uses hypothetical USD cents and a hypothetical 100 cents/minute
effort rate. Four separate 100-unit jobs share a 25-minute/3000-cent setup.
Each costs 500 cents and 35 minutes, with 18000-cent nominal reward and an
explicit 8000-basis-point collection assumption. All four fit the supplied
deadlines: 400 described units, 165 minutes, 5000 direct cents, 16500 effort
cents, 57600 scenario-value cents, **36100 net scenario cents**. This is an
arithmetic illustration, not $361 revenue, not a live lead, and not a promise
that four real jobs are available.

The isolated 200-cent/30-minute task is excluded, the unvalued token reward
gets no invented exchange value, an attractive peer-owned job remains
excluded, and a missed-deadline job stays visible. A high nominal discovery
reward competes using its explicit 20% scenario assumption rather than its
headline price. Scenario times are frozen; rerunning the fixture later does
not certify that the September 15 deadline is still current.

## Evidence and operational handoff

Tests include independent subset arithmetic, full permutation checks of the
scheduling reduction, hundreds of seeded exact comparisons, cutoff-bound
comparisons against independently computed optima, shared-setup synergy,
unit counting, cash/time/deadline boundaries, tampering, ordering, malformed
input, FIFO/symlink handling, and normal/optimized CLI byte identity.
`benchmark.py` reports actual timing, source-input/report digests, and the
remaining gap for reproducible synthetic 16/64/256-job cases. Synthetic tests
are not evidence of real delivery, acceptance, payment, or expected earnings.

To use a result operationally: return to the existing work record, refresh
claims and deadlines, check the source payout terms, and acquire the existing
single-writer claim before acting. A favorable scenario cannot grant any of
those permissions. All output authority flags remain false.
