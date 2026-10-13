# UIOWA-049 — technical-debt investment analysis kit

An executable, dependency-free, **service-level** decision aid for UIOWA-049.
It connects recurring support work, architectural dependencies and uncertain
remediation effort to explicit competing investment scenarios. It does not
judge individual engineers, calculate maturity scores, make University findings,
prescribe a vendor, or approve an investment.

Operation: `uiowa-049-debt-9a1a5dca-20260919`.
Source/implementation: ZZ-KESTREL-9A1A5DCA / GPT-6 Astra Pro.
Work record: Commons issue #16096. All checked-in examples are **SYNTHETIC**.

## Run from the repository root

Use Python 3.10 or later; no installation, network, credential or third-party
package is needed by this module. The tested runtime is recorded in the PR.
The commands create only a new report directory. Existing directories are
refused rather than overwritten.

```sh
python -m revenue.uiowa_rfq_18649_debt \
  revenue/uiowa_rfq_18649_debt/examples/synthetic-register.json \
  --budget-hours 50 --horizon-weeks 12 --output-dir /tmp/debt-example

python -m revenue.uiowa_rfq_18649_debt \
  revenue/uiowa_rfq_18649_debt/examples/synthetic-register.json \
  --budget-hours 50 --horizon-weeks 12 --require OBSOLETE \
  --output-dir /tmp/debt-risk-scenario

python -m unittest -v revenue.uiowa_rfq_18649_debt.test_debt
python -O -m unittest -v revenue.uiowa_rfq_18649_debt.test_debt
```

On Windows, replace `/tmp/...` with a new directory appropriate to the machine.
A required item is an **analyst's scenario constraint**, not an organizational
mandate or approved work assignment. No calendar events, emails, provider calls,
repository changes, purchases or deployed changes are made by this program.

Outputs: `analysis.json` (complete scenario and item records), `analysis.md`
(readable decision worksheet), and `priorities.csv` (spreadsheet-readable
projection). The JSON register is the editable source of truth; the reduced CSV
is **not** a lossless register round-trip format. Text cells that could be
interpreted as formulas are prefixed with an apostrophe; numeric negatives remain
numeric. Exit codes: 0 = scenarios available (possibly defer all), 2 = input or
I/O error, 3 = no feasible portfolio satisfying the requested scenario. Code 3
still writes an explicit infeasibility report. Writes are create-exclusive, not
an atomic multi-file transaction; an I/O failure can leave a partial new directory.

## Proposed method, not a validated institutional benchmark

The objective is **net support hours saved within the declared horizon**.
This is a deliberately narrow, inspectable design choice, not an empirical
benchmark or a claim that support-hour payback captures all service value.
Service consequence and qualitative criticality remain separate on every row.
A critical-risk item not selected by the payback objective gets an explicit
investigation question before anyone considers deferral.

For each item:

```
benefit_weeks = max(0, horizon_weeks - benefit_delay_weeks)
saved_low  = weekly_support_hours.low  * reduction_pct.low  / 100 * benefit_weeks
saved_high = weekly_support_hours.high * reduction_pct.high / 100 * benefit_weeks
net_low    = saved_low  - effort_hours.high
net_high   = saved_high - effort_hours.low
```

All arithmetic uses integer hundredths of an hour; decimal strings in the report
retain exact two-decimal results. Inputs are integer hours and integer percentage
points. Values below one hour can be represented in the narrative but are not
accepted as fractional-hour input estimates in v1. Do not silently round them.

The **conservative** scenario maximizes summed `net_low`; the **optimistic** one
maximizes summed `net_high`. Both use the same capacity constraint: the sum of
selected **upper** effort bounds must fit the supplied budget. Ties use the other
endpoint, then lower upper-bound effort, then lexicographic selected IDs. The
empty portfolio is permitted unless required items make it inadmissible.

These are endpoint sensitivity scenarios, not probabilities, expected values,
statistical confidence intervals or guaranteed savings. Upper/lower endpoint
co-occurrence is an assumption, not a modeled dependence distribution. The
benefit delay must already include implementation, prerequisites, adoption and
any relevant change windows. The model does **not** derive a feasible calendar
or role-by-role resource schedule and does not resolve the actual staff capacity.

### Dependencies and workload accounting

Every selected item requires its full transitive dependency closure. A shared
prerequisite's effort is counted exactly once. Negative-payback prerequisites
remain eligible when they enable a positive portfolio; this is not a greedy
standalone ranking. Self-dependencies, missing dependency IDs and cycles are
input errors. Unknown estimates propagate through dependencies.

At most one item may be selected within the same non-null `benefit_pool`, and
at most one within the same non-null `alternative_group`. Pools represent the
**same underlying support burden**, not just the same department or service.
This prevents two remediations claiming the same saved hours. Alternative groups
represent mutually exclusive investment approaches even where their burden
pools differ. A shared zero-benefit prerequisite normally has `benefit_pool:null`.

If several remediations truly deliver additive benefits against one burden, do
not manufacture separate pool labels to get a larger number. Either establish
non-overlapping measured portions of the workload, or represent the combined
investment as one explicitly estimated option with its own dependencies. This
model does not estimate nonlinear interactions or partial overlap.

The solver enumerates every feasible portfolio in an explicitly selected cohort
of 1–18 items, pruning only capacity and exclusion violations. It reports its
feasible count and never silently truncates. This bound makes exactness and run
cost predictable. For a larger backlog, an analyst must define and disclose a
coherent decision cohort, retaining cross-cohort dependencies and overlapping
burdens in the review; independent cohort solutions are **not** automatically a
globally feasible or globally optimal portfolio.

## Editable register contract

Root fields must be exactly `schema`, `evidence_class`, `items`.
`schema` is `tjlabs.technical-debt-register/v1`; evidence class is `SYNTHETIC`
or `ASSESSMENT_INPUT`. Changing that label does not authenticate any source.

Every item contains the following fields; unknown fields are rejected to expose
misspellings and incompatible versions instead of silently discarding them.

| Field | Meaning / accepted form |
|---|---|
| `id` | Unique 1–64 character ASCII identifier, letters/digits/dot/underscore/hyphen; first character alphanumeric. |
| `service` | Service context, not an individual performance target. |
| `category` | `RECURRING_SUPPORT`, `OBSOLESCENCE`, `ARCHITECTURE`, or `MAINTAINABILITY`. |
| `summary` | Specific change or investigation proposal. |
| `service_impact` | `LOW`, `MODERATE`, `HIGH`, `CRITICAL`; a supplied qualitative characterization, not a numeric optimizer weight. |
| `service_consequence` | User/service consequence and context supporting the characterization. |
| `owner_role` | Proposed reviewing role; not a confirmed assignment. |
| `evidence_refs` | List of supplied source IDs or locators, without duplicates. |
| `estimate_basis` | `OBSERVED`, `ESTIMATED`, or `UNKNOWN`. Observed needs references; source verification remains an analyst task. |
| `effort_hours` | `{low, high}` nonnegative integer interval, upper bound ≤1,000,000; or `null`. |
| `weekly_support_hours` | Nonnegative integer interval for the affected burden, same bounds; or `null`. |
| `reduction_pct` | Integer percentage interval, 0≤low≤high≤100; or `null`. |
| `benefit_delay_weeks` | Nonnegative integer, maximum 520; includes implementation and dependency lead time. |
| `benefit_pool` | Shared burden identity or `null`; required when known potential benefit is positive. |
| `alternative_group` | Mutually exclusive strategy identity or `null`. |
| `dependencies` | Unique IDs in this cohort; prerequisites must themselves be selected. |
| `revisit_trigger` | Evidence or changed circumstance that should reopen the decision. |

All text is nonblank and at most 2,000 characters; line controls and invalid
Unicode surrogates are rejected. Lists are bounded at 100 entries. Missing
numeric estimates are `null`, never zero. `UNKNOWN` must preserve at least one
null interval; an `ESTIMATED` row can also have a missing interval and will remain
unscored. Bounds, exact JSON types (including bool vs int), duplicate keys,
non-integer/nonfinite numbers, oversized files and malformed UTF-8 are checked.
Raw ingress is bounded to 2,000,000 bytes. Input integer tokens are limited before
conversion. This is a trusted-process data-validation library, not an execution
sandbox for arbitrary hostile Python code.

API:

```python
from revenue.uiowa_rfq_18649_debt import load_register, analyze
packet = load_register(open('register.json', 'rb').read())
report = analyze(packet, budget_hours=50, horizon_weeks=12, required_ids=())
```

The normalized register digest is order-independent for items, dependencies and
evidence references. The report digest covers canonical JSON excluding its own
`report_sha256` field. These are reproducibility digests, not digital signatures,
source authentication, evidence currentness or approval receipts.

## Worked fictional choice

`examples/synthetic-register.json` contains eight fully fictional choices across
ESS-like, RIS-like and IAM-like services plus a shared prerequisite. It is not
an inventory of University of Iowa systems or a finding about any institution.
Every `SYN-*` reference denotes a fictional case in this example, not an external
source. Each input is an assumption; no University interviews or logs were used.

At 50 hours capacity / 12 weeks:

| Scenario | Selected | Upper effort | Net hours, low..high |
|---|---|---:|---:|
| Conservative | BASE + RETRY + SYNC | 32 | 42.00..120.00 |
| Optimistic | AUTOMATE + BASE + RETRY | 40 | 4.00..140.00 |

The recurring retry and reconciliation burdens support the conservative
portfolio. Speculative automation changes the optimistic portfolio and needs
validation. The larger import replacement competes with retry repair against
the **same** burden, so both cannot be counted. POLISH fits the budget but has
no positive modeled payback even at the upper endpoint; its revisit trigger
preserves a reasonable case to defer. UNKNOWN retains missing implementation
and reduction estimates. OBSOLETE has critical qualitative continuity risk but
little modeled support saving: its nonselection is **not** a recommendation to
ignore risk. The second command explicitly tests including it.

For each synthetic reference, collect the following in a real assessment rather
than inventing evidence:

| Fictional reference | Evidence question for a future populated register |
|---|---|
| SYN-BASE | Which interfaces and teams depend on the contract, and is enablement already included in dependent estimates? |
| SYN-RETRY | What period, demand volume and incident classes establish the repeated retry workload? |
| SYN-REPLACE | Is this replacing the same burden as RETRY, and what lead time and migration effort are omitted? |
| SYN-SYNC | Are these reconciliation hours genuinely distinct from retry-support hours? |
| SYN-AUTOMATE | Which representative request sample could narrow the unusually wide workload and reduction bounds? |
| SYN-POLISH | What specific service consequence would justify disrupting stable low-use code? |
| SYN-OBSOLETE | What current component-lifecycle evidence and continuity consequence justify risk treatment independent of payback? |
| SYN-UNKNOWN | What bounded discovery task can establish the missing effort and reduction estimates? |

## Analyst worksheet and integration

Before numerical comparison, trace each backlog entry to the service, observation
period, workload denominator, consequence, source version, and reviewing role.
Check for selection bias (only painful incidents), peak-cycle effects, overlapping
support records, already-completed prerequisites and sunk costs. Reject individual
engineer rankings. Discuss dependencies and service risk with the appropriate role.

After analysis, compare both portfolios, inspect every unknown and high-impact
nonselection, validate delays, and record the analyst's actual disposition and
reason outside the hypothetical scenario. Compare an explicit required-item
scenario when risk or a genuine obligation must dominate payback; document who
established that constraint. Do not interpret tool input as proof of an obligation.

`analysis.json.items` retains IDs, evidence references, service consequences,
estimates, dependency closure and revisit triggers. A report or roadmap adapter
can carry these fields as **scenario evidence** without promoting them to
verified findings or adopted recommendations. Existing compiler/workbench paths
are untouched. Recalculate after a source, estimate, dependency or horizon change.

## Test coverage and scope

The retained suite has 30 test methods, including 120 seeded randomized cohorts
checked against an independent `itertools.combinations` oracle, an exhaustive
18-item (262,144 feasible subsets) zero-cost boundary, dependencies, shared costs,
negative enablers, both exclusion rules, missing-estimate propagation, required
scenarios, infeasibility, uncertainty, zero capacity, delays/fractional outputs,
canonical permutation invariance, strict ingress and CLI export/no-overwrite.
Run under normal and real optimized Python. This is selected-package evidence,
not full-repository CI, current institutional evidence or actual savings.
