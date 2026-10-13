# SOL-PARETO — state-conditioned safe-own SELL objective

Operation: `TITAN-V3-STATE-CONDITIONED-SAFE-OWN-OBJECTIVE-20260910-01`

Slack claim: `#titan-kaggriculture`, timestamp `1789070901.505289`.

## Why this lane

TITAN's selected SELL optimizer ranks every plan with

```text
own receipts + continuation value - rival receipts
```

PR #11965 showed that deleting the rival term globally can improve TITAN's own
terminal cash, but a separate coefficient-frontier pilot found that no fixed
rival weight dominates every development state. This carrier tests a narrower,
state-local rule instead of fitting another global coefficient.

## Mechanism

For each eligible strict-dominance `optimize_lot` call, the overlay:

1. executes the exact incumbent optimizer and retains that result object;
2. executes the same optimizer a second time on the same public inputs, same
   candidate family, same physical callback, and same canonical scenarios, with
   score element zero reweighted from `own_value - rival_receipts` to
   `own_value`;
3. re-evaluates the authored reference, incumbent plan, and own-value plan with
   the unmodified receipt scorer; and
4. selects the own-value plan only when **every** canonical scenario proves:
   - own value is strictly greater than both the authored reference and the
     incumbent-selected plan; and
   - true relative value is not below the authored reference.

Any source drift, malformed result, candidate exception, non-strict acceptance
rule, forced-feasibility path, infeasible result, tie, or failed safety
predicate returns the first incumbent result object unchanged.

The selector does not read seed identity, opponent labels, private shed or
orders, future replay data, or a learned model. It does not add scenarios,
plans, slots, inventory, or money. It changes no canonical file.

## Exact binding

The overlay binds the selected archive's `selected_sell_core.py` Git blob
`f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`, the exact
`MarketPath.score` and `optimize_lot` signatures, and source anchors for both
seams. It is designed for the exact package already exercised by PR #11965:

- archive SHA-256: `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`
- source-manifest SHA-256: `3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469`
- 428,158 compressed bytes / 109 runtime files
- direct stacked parent: `b6b9a8a4ca26152bbfe1a3833380ca885e5c4cae`

## Focused evidence

`test_safe_own_objective.py` contains eleven predecessor/fail-closed contracts:

- the safe own frontier is selected;
- a second-pass exception returns the exact incumbent result object;
- a relative-value regression returns the exact incumbent result object;
- non-strict rules execute the incumbent exactly once and return its object;
- score tuple shape and changed-field closure;
- source/blob/signature drift rejection;
- idempotent installation;
- own-value dominance over both reference and incumbent;
- relative-value safety versus reference;
- malformed-plan rejection; and
- non-finite evidence rejection.

`MECHANISM-WITNESS.json` demonstrates one candidate that gains own value in all
three modeled same-turn scenarios while staying above reference relative value,
and an otherwise identical candidate rejected when one relative-value row falls
below reference.

## One-shot exact-package panel

The workflow uses the reviewed PR #11965 archive carrier, evaluator
materializer, action-custody binder, comparator, and admission gate rather than
creating a second simulation stack. The precommitted grid is:

- opponents: exact public Arlene and exact frozen V1;
- eight SHA-derived fresh seeds;
- both candidate seats;
- 32 cells per arm / 64 complete official-interpreter games total;
- pinned `kaggle-environments==1.32.7`;
- candidate returned-action capture before interpretation; and
- exact control/candidate archive-tree identity before and after the panel.

The panel retains evidence even for `REJECT` or `INACTIVE`. Promotion requires
nonzero returned-action activation, positive own-cash and margin evidence,
nonnegative opponent-by-seat strata, and zero new losses under the inherited
gate. A positive result is only an integration input.

## Boundary

This branch is additive evidence and an isolated executable overlay. It does
not mutate the canonical runtime, `TITAN-CONFIG.json`, selected archive, release
pointer, provider state, Kaggle state, leaderboard submission, or one-tree
integration branch. It does not supersede the fixed-weight frontier, #11965,
#12040, the strict-pressure factorial, or the one-tree publisher.
