# Fictional fixture specifications

These specifications are rehearsal assumptions. An application owner must
supply the real behavior contract before using them for application acceptance.
All subjects, service names, amounts, roles, and evidence pointers are invented.
There are no production-derived records or operational credentials.

## Shared temporal contract

Each example uses a half-open effective interval **[start, end)**, with explicit
UTC offsets and UTC-normalized generated inputs. Start is inclusive; end is
exclusive. This is a chosen reference rule, not a claim about University systems.

| Boundary | Generated instant | Expected interval membership |
|---|---|---|
| before | start − 1 microsecond | false |
| at_start | start | true |
| inside | midpoint strictly between start and end | true |
| at_end | end | false |
| after | end + 1 microsecond | false |

A complete five-case plan is complete only for this selected temporal partition.
It does not cover the complete input space, all business rules, or release
readiness. The generator refuses a requested interior point when the interval
has no representable interior microsecond.

## ESS: term effective-time behavior

**Fictional question:** Is a synthetic term active at the supplied instant?

Generator: `term_window`. Output expectation contains `term_active` and the
Unicode label `Synthetic term — Δ`. Inputs use `SYNTHETIC-0001`, not a real
student identifier. The tool does not produce enrollment decisions.

`ESS-TERM` exercises all five boundaries with a source and target interface
label of `fictional-api-v1`. `ESS-LEGACY` exercises only start/interior/end; its
source label is `fictional-api-v0`, its owner is unknown, and its recorded
refresh is older. This intentionally creates a partial-boundary and
compatibility-review conversation instead of silently declaring failure.

**Not modeled:** prerequisites, concurrent enrollment, add/drop rules, holds,
capacity, fee calculation, degree audit, accessibility, local calendar/DST rules,
locale-specific presentation, or institution-specific exception handling.

**Evidence to request:** the actual term-boundary rule, its revision, one
representative recent change, the target interface contract, the selected
fixture's refresh record, and an independently recorded application run.

## RIS: funding effective-time behavior

**Fictional question:** Is an invented funding period effective at this instant?

Generator: `funding_window`. Expected fields are `funding_period_active` and
`allocation_decimal`. The invented allocation is the string `"1000.00"` while
active and `"0.00"` outside the interval. This deliberately avoids treating a
binary floating-point number as a financial calculation. No money is moved and
no actual award or ledger is represented.

`RIS-FUNDING` crosses the fictional 2026/2027 year boundary and leaves its target
interface version unknown. `RIS-RETIRED` retains an older definition whose
retirement has taken effect at the rehearsal cut-off but whose cleanup or
retention-disposition evidence is missing.

**Not modeled:** sponsor-specific rules, currencies, cost sharing, amendments,
indirect-cost rates, financial reconciliation, authorization, or multi-award
attribution. The allocation expectation is a simple fixture value, not advice
about accounting, a grant policy, or a financial control.

**Evidence to request:** the actual effective-period rule, versioned interface,
maintenance owner, retention/cleanup rationale for obsolete fixtures, and the
record of a controlled application test of the real rule.

## IAM: contractor-role effective-time behavior

**Fictional question:** Which invented role is effective at the supplied instant?

Generator: `role_transition`. The expected role array is
`["synthetic-contractor"]` during the interval and empty outside it. At and after
expiry, `stale_previous_role_must_not_persist` is true. This is a reference
expectation: no identity system is queried and no entitlement is changed.

`IAM-CONTRACTOR` exercises a complete known metadata path with an invented
3–8 hour maintenance range. `IAM-UNKNOWN` intentionally lacks its maintenance
owner, refresh date, refresh pointer, and effort range. Those fields produce
unknowns rather than a made-up low readiness score.

**Not modeled:** distributed propagation, caching, session invalidation,
reconciliation latency, shared accounts, nested groups, multiple concurrent
roles, sequential sign-off processes, or real privilege semantics. Absence of a role in the
reference output does not establish that access was revoked in any system.

**Evidence to request:** the actual effective-time/propagation contract, the
owner of fixture maintenance, a version-bound refresh example, and observed
results from a controlled identity-lifecycle test environment.

## Adapting a reference expectation

Record a changed business rule as a new definition version; update the purpose
and limitation notes as well as the inputs. Do not rewrite an expectation solely
because the system under test returned a different answer. First establish
whether the contract, adapter, fixture, or implementation needs correction.
Keep the original output and discrepancy as evidence of the investigation.

The bundled examples are an executable starting point for interview preparation,
not an institution-specific oracle library. An application adapter and actual
application observations remain deliberately out of scope.
