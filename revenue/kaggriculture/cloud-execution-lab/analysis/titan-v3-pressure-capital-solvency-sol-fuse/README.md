# TITAN V3 — final-pressure acquisition-solvency interlock

Operation: `TITAN-V3-PRESSURE-CAPITAL-SOLVENCY-20260910-01`

Exact base: `2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb`

## Defect

Current `main.py` intentionally runs public market-pressure ordering after the
operating-stock and early-capital passes. Pressure preserves lot quantities and
barriers, but changing a SELL lot's market index changes how it interleaves with
an unknown simultaneous rival order. Actual own receipts before a later HIRE,
BUY_LAND, BUY_SEED, or BUY_ANIMAL can therefore fall below the amount assumed by
the pre-pressure returned queue.

The predecessor-killing official-interpreter fixture is:

- own cash `$176`, quadrants `NW+NE`, shed `CARROT 10 + MILK 10`;
- own queue `SELL CARROT 10, SELL MILK 10, BUY_LAND`;
- rival queue `SELL CARROT 10` at index 0;
- current pressure scores `MILK 210 > CARROT 22`, so the final pass swaps them.

The pre-pressure queue realizes exactly `$2,000` and unlocks `SW`. The pressured
queue realizes `$1,988` before `BUY_LAND`, so the engine rejects the land order.
No quantity, barrier, action cardinality, or feature-local contract changes.

## Candidate

`pressure_capital_solvent.py` is a stateless returned-action interlock:

1. verify pressure changed only a permutation of the executable market prefix;
2. keep pressure unchanged when no acquisition follows the changed rows;
3. otherwise replay the exact supported fixed-cost prefix from observed starting
   cash while crediting **zero** SELL proceeds;
4. keep pressure only when starting cash alone funds every such acquisition;
5. fail closed on BUY_PRODUCT, source/grammar ambiguity, or contract drift by
   returning the exact already-guarded pre-pressure action.

`candidate.py` binds exact Git blob IDs for current `main.py`, `titan_runtime.py`,
`early_capital.py`, and `pressure_priority.py`. It installs the interlock at the
existing `FinalPressureAgent._early_capital_selected` seam without modifying
canonical source, config, archive, pointer, provider state, or submission state.

## Evidence

Focused contracts cover the official predecessor, exact pressure ordering,
fixed-price HIRE/LAND/SEED/ANIMAL replay, market-order truncation, variable-price
fail-closed behavior, action/multiset/suffix integrity, immutability, stage order,
deadline-fallback nonactivation, source identity, and guard-error fallback.

`run_panel.py` delegates process isolation and official-engine provenance to the
landed paired runner. The panel compares canonical and candidate on identical
opponent/seed/seat cells. Zero activation or a score/outcome miss is a `REJECT`,
not evidence of strength.

## Commands

```bash
python -B test_pressure_capital_solvent.py -v
python -B test_candidate.py -v
python -m py_compile *.py

python run_panel.py \
  --head "$(git rev-parse HEAD)" \
  --seeds 2611092201,2611092202,2611092203,2611092204,2611092205,2611092206,2611092207,2611092208 \
  --opponents arlene,apex,kaito_v43,cok_v10,public_bt12,v1 \
  --workers 4 \
  --output PRESSURE-CAPITAL-PANEL.json \
  --markdown PRESSURE-CAPITAL-PANEL.md
```

No Kaggle upload or canonical promotion is authorized by this analysis branch.
