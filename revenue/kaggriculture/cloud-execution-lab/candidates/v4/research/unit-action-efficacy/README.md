# UNITWASTE — source-bound unit-action efficacy evidence

UNITWASTE is an evidence-only current-V4 research packet. It does **not** add a
controller, retask an actor, change a returned action, or alter runtime/default/
config/archive/Kaggle bytes.

## Why this exists

The official interpreter executes the farmer first and hands in index order,
mutating shared farm/private state after every actor. That creates a negative
counterpart to positive same-callback pipelines: a later co-located actor can
become a deterministic no-op because an earlier actor already consumed the
same one-shot state.

`unit_action_efficacy.py` replays only the official unit phase on private copies
of the exact returned action. It preserves the engine's atomic same-crop PLANT
preflight before dispatch, then compares farm/private state before and after
individual actor execution. Its predecessor attribution is deliberately narrow:
only a later `CARE`, `WATER`, `COLLECT_FERTILIZER`, or `HARVEST` is tagged when
an earlier actor in that callback **successfully changed the same tile using the
same operation**. Other no-ops remain unclassified rather than guessed.

## Exact source boundary

The tool refuses source drift from authenticated GitHub Actions artifact
`10175943272`, inner native tar SHA-256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`:

- official engine Git blob `3c202c7ee921da239356789e266b694635103fc4`
- native `main.py` Git blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`

## Current-native panel

Eight fixed seeds `{17, 101, 6607, 9922999, 2026091201, 2026091207,
2026091213, 2026091219}` were replayed in **both seats** versus the official
starter: 16/16 complete cells, 11,504 native callbacks and 105,136 non-PASS unit
actions.

The exact interpreter replay found 792 no-op non-PASS unit actions overall.
Most are not assigned a cause by this packet. The strict predecessor rule does,
however, prove **120** later-actor same-target no-ops:

- `CARE`: 48
- `WATER`: 44
- `COLLECT_FERTILIZER`: 24
- `HARVEST`: 4

`NATIVE-CENSUS.json` contains per-operation changed/no-op totals, per-cell
duplicate counts and scores. Re-running `unit_action_efficacy.py` for a cell
emits the exact seed/seat/step/actor/predecessor coordinates. This is **not** a
claim that 120 actions can safely be recovered. A replacement must independently
prove its route, inventory, target, timing, capacity, and rejoin invariants.
UNITPIPE/LABORFLOW/current route owners can consume the tracer instead of
rediscovering the waste.

## Validation

```bash
python -B test_unit_action_efficacy.py
python -O -B test_unit_action_efficacy.py
python -m py_compile unit_action_efficacy.py test_unit_action_efficacy.py
```

Authored suite: 8/8 normal + 8/8 optimized. The published native receipt was
produced by running one process per seed/seat so agent globals cannot leak
between games, for example:

```bash
python -B unit_action_efficacy.py --package "$PKG" --seed 17 --seat 0 --output 17_0.json
```

No runtime activation or economic uplift is asserted here.
