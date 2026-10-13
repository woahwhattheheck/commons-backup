# TITAN V3 route-reference echo guard — SOL-ACCRUAL

Operation: `titan-v3-route-reference-echo-20260909-sol-accrual-01`

## Exact defect

The selected SELL consumer constructs each optimizer reference in this order:

1. current inherited sale plus due scheduler intent;
2. still-pending scheduler rows;
3. future `SELL` rows already present in the unchanged controller route.

When a single-product plan wins admission, canonical `FrozenSelected.transform()`
checkpoints the entire selected future plan in `self.planned`. On a later turn,
that checkpoint is added to the route's inherited sale again. A route-owned
quantity can therefore become scheduler-owned intent and be counted twice.

The defect is stateful and can be invisible in a one-turn unit test: the first
returned action can remain correct while the next observation reconstructs a
larger reference and later materializes more liquidation than the optimizer
selected. This is a plausible cash/score regression mechanism, but this packet
makes no score or leaderboard claim.

## Exact source boundary

The audit pins and reads once:

- current `frozen_selected.py` Git blob
  `fc7baf5c179818a55037f6a61d92984d81d1a21c`;
- canonical `main.py` Git blob
  `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`;
- frozen V1 scheduler blob
  `cbc502a92fe9d790cfaf763f6990d1057bc9b82d`;
- frozen V2 scheduler blob
  `7c068b7078c3d7c09bb3836590ad42b0af934cdf`.

The V1/V2 source contrast is attribution context. The candidate executes the
current V3 canonical entrypoint and current feature configuration.

## Correction contract

`RouteEchoGuardedFrozenSelected` delegates the complete transform first. It
never edits the current returned action. For a newly admitted **single-product**
plan, it verifies the exact canonical checkpoint, then stores only the positive
future quantity above the inherited route `SELL` quantity at the same step.
That makes the next turn reconstruct the selected total once:

```text
inherited route quantity + scheduler-owned excess = selected quantity
```

The guard is intentionally conservative:

- a plan that undershoots a fixed future route sale is not representable and
  retains predecessor state;
- malformed plan/route rows retain predecessor state;
- checkpoint drift retains predecessor state;
- joint-plan behavior is byte-for-byte predecessor behavior;
- no current queue, controller route, canonical source, configuration, archive,
  release pointer, provider state, or Kaggle submission is modified.

`candidate.py` reads and Git-blob-verifies canonical `main.py` once, executes it
in a private module, preserves its `FinalPressureAgent` carrier, then reclasses
only the already-wired frozen consumer after canonical initialization. The
controller, production owner, seed budget, spatial wrappers, recovery state,
and whole-call deadline remain canonical.

## Evidence gates

The focused suite includes:

- pure exact-route subtraction and malformed-input contracts;
- an unrepresentable route-floor denial;
- a real `FrozenSelected.transform()` two-turn predecessor witness where route
  quantity `2` becomes `4` in the second reference;
- the guarded counterpart, with byte-identical current actions and stable
  second reference;
- a real canonical constructor/MRO/consumer-identity test.

The source audit additionally inventories all non-operating inherited route
sales and requires at least one static same-day row inside the inherited horizon.
That is an applicability surface, not dynamic optimizer activation.

## Reproduce

From the repository root:

```bash
export PYTHONDONTWRITEBYTECODE=1
LAB=revenue/kaggriculture/cloud-execution-lab
LANE=$LAB/analysis/v3-route-reference-echo-sol-accrual
python -B -m py_compile "$LANE"/*.py
python -B -m unittest discover -s "$LANE" -p 'test_*.py' -v
python -B "$LANE/audit.py" \
  --lab "$LAB" \
  --output /tmp/titan-v3-route-reference-echo-audit.json \
  --require-opportunity
python -B "$LAB/build_integrated.py" --check
```

No official-engine games are authorized by this packet. A later matched panel
must first demonstrate dynamic `route_reference_echo.changed=true` activation,
bind the exact candidate closure, use both seats and identical cells, and rank
own cash before rival-denial margin.
