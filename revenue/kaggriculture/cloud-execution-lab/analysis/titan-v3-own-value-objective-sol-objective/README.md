# TITAN V3 own-value SELL objective

Operation: `titan-v3-own-value-objective-20260909-sol-objective-01`

## Hypothesis

The canonical V3 SELL optimizer ranks and admits plans through
`MarketPath.score()[0]`. At the pinned source blob, that field is:

```python
own_cash + carry - rival_cash
```

The official tournament's primary metric is the candidate's own terminal cash.
Subtracting rival receipts inside the policy objective can therefore reverse the
choice between two legal plans: a plan with lower own value can win only because
it denies more cash to the opponent.

This candidate changes exactly one semantic field:

```text
MarketPath.score[0]:
    own_cash + carry - rival_cash
->  own_cash + carry
```

The candidate recovers that value from the incumbent tuple as
`score[0] + score[2]`. It does not copy or alter market receipts, continuation
value, rival schedules, candidate enumeration, feasibility, capacity, target
ownership, queue materialization, acquisition ordering, runtime deadlines, or
the evaluator.

## Boundary and binding

- Canonical `selected_sell_core.py` Git blob:
  `f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`
- Starting main commit:
  `bcf6e388b8b8d4fdca94f09d7f5493269ee14d22`
- Runtime overlay: `own_value_objective.py`
- Candidate entrypoint: `candidate.py`
- Canonical files modified: **none**
- Kaggle/provider/pointer/config action: **none**

The overlay refuses to install unless all of the following remain true:

1. the loaded file is the exact canonical-path `selected_sell_core.py`;
2. `MarketPath.score` retains its pinned call signature;
3. the incumbent rival-subtracted return expression is still present;
4. no conflicting runtime overlay is already attached.

The workflow independently verifies Git blob identities before importing the
candidate. Runtime score outputs must be an exact finite four-tuple, and the
recovered own value cannot be below realized own cash.

## Mechanism witness

`mechanism_witness.py` includes an explicit inversion:

| Plan | Own value | Rival receipts | Incumbent objective |
|---|---:|---:|---:|
| rival suppression | 100 | 0 | 100 |
| leaderboard cash | 112 | 30 | 82 |

The incumbent objective selects `rival suppression`; the candidate objective
selects `leaderboard cash`, increasing the optimized own value by 12. A second
case proves the overlay leaves an already aligned ordering unchanged.

## Tests

Run from this directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  test_own_value_objective.py test_compare.py
python -m py_compile \
  own_value_objective.py candidate.py mechanism_witness.py compare.py \
  test_own_value_objective.py test_compare.py
python mechanism_witness.py
```

The local suite contains 22 contracts covering:

- the algebraic recovery identity and one-field mutation;
- rival-receipt invariance of the candidate objective;
- malformed, boolean, nonfinite, and negative-implied-carry rejection;
- exact source path/signature/expression binding;
- idempotent install and conflicting-overlay refusal;
- complete paired evaluator grids and duplicate-cell rejection;
- engine/loader/evaluator/seed/opponent/limit provenance equality;
- own-cash, margin, action-trace, and first daily-bank deltas; and
- upside, mixed, dormant, and regression classifications.

## Hosted evidence

The path-scoped workflow runs the canonical V3 control and this candidate under
the merged process-isolated official-interpreter evaluator:

- Python 3.11;
- `kaggle-environments==1.32.7`;
- engine ref `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`;
- canonical eight-seed panel;
- both player seats;
- frozen V1 and public Arlene opponents;
- identical RNG and timeout settings.

That is 32 cells per arm and 64 total games. The artifact retains both raw
reports, progress snapshots, exact-head/source receipts, the mechanism witness,
and a machine-readable paired report. A result may be `UPSIDE_SCREEN`,
`MIXED_SCREEN`, `NO_ACTION_CHANGE`, or `REGRESSION_SCREEN`; score direction does
not get hidden behind a CI pass/fail. Invalid provenance, incomplete games, or
malformed evidence do fail the workflow.

This experiment cannot authorize promotion or make a hosted leaderboard claim.
