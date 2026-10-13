# Revenue Opportunity Portfolio

This package closes a portfolio-level execution gap in Commons: source-bound leads, contests, bids, services, and bounties can each be valid while the combined set still exceeds human/agent capacity, conflicts on ownership, depends on blocked infrastructure, or mixes currencies that cannot honestly be compared.

`opportunity_portfolio` compiles those records into a deterministic **human-reviewable** execution portfolio. It is deliberately not an outreach, submission, payment, scheduling, or revenue-recognition system.

## Trust boundary

The opportunity packet does **not** choose its own evaluation time. Callers pass `trusted_as_of` out of band. Every opportunity must bind:

- a source reference, SHA-256 digest, observation time, and freshness limit;
- a deadline;
- source-backed eligibility status;
- exact integer minor-unit value and optional probability basis points with separate evidence digest;
- named capacity consumption;
- owner/collision state;
- blockers, dependencies, and optional mutually-exclusive group.

A probability without evidence is rejected; missing probability evidence routes the opportunity to `QUALIFY`. Unknown eligibility/owner state cannot execute. Closed deadlines and owner collisions `HOLD`. Open blockers and impossible individual capacity `BLOCKED`.

## Money and objective

Money is integer-only. Expected value is represented exactly as:

`amountMinor * probabilityBps / 10000`

No binary floating point is used. The compiler **never invents FX**. A portfolio with more than one currency requires an explicit `currencyPriority` policy that covers the exact currency set; otherwise the entire executable set is held. This is an operator priority order, not an exchange-rate assertion.

For up to 26 runnable opportunities, the compiler performs an exact deterministic branch-and-bound search across capacity, dependency, and exclusivity constraints. It lexicographically maximizes the full vector of source-backed expected-value numerators in the declared currency order, then uses the corresponding face-value vector as a deterministic tie-breaker, then the lexicographically smallest opportunity-ID set. No currency is converted into another.

## States

Per opportunity:

- `EXECUTE_NOW`: selected by the exact constrained portfolio solver;
- `READY_NOT_SELECTED`: valid but displaced by constraints/objective;
- `QUALIFY`: evidence/freshness/ownership/capacity vocabulary is incomplete;
- `BLOCKED`: a concrete blocker/dependency/capacity condition prevents execution;
- `HOLD`: hard authority or validity failure.

The strongest receipt state is `PORTFOLIO_READY_FOR_HUMAN_EXECUTION_REVIEW`. All external-action authority flags stay false.

## CLI

```bash
python -m revenue.opportunity_portfolio.cli compile opportunities.json \
  --trusted-as-of 2026-09-13T10:00:00Z \
  --receipt portfolio.json \
  --markdown portfolio.md

python -m revenue.opportunity_portfolio.cli verify portfolio.json
```

Verification checks the receipt digest, normalized-input digest, and deterministic full recompilation.

## Safety / authority ceiling

This package cannot send outreach, contact a buyer, submit a bid, claim a bounty, spend funds, sign or amend a contract, execute/refund a payment, mutate provider scheduling, infer buyer acceptance, or recognize revenue. Secret-shaped material is refused. It prioritizes evidence; it does not create commercial authority.
