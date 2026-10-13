# V5 overflow-safe DROP streaming (research-only)

Status: **default OFF / not wired into canonical runtime**.

## Engine theorem

Pinned Kaggriculture unit mechanics distinguish two shed operations that look similar but have different overflow behavior:

- `DROP`: for every carried stack, deposit at most current shed room and then delete the entire carried key. Any remainder is destroyed.
- `PLACE <item> <qty>` while standing at shed access: deposit only the requested amount that fits, subtract only that deposited amount, and preserve the remainder in the worker pocket.

Worker pockets have no capacity bound. Unit actions execute before market rows in the same engine step.

Therefore, for a worker carrying one sale good at shed access with `carried > shed_room`, replacing its selected `DROP` by `PLACE item shed_room` (or `PASS` when `shed_room == 0`) gives the same immediate shed post-unit state while preserving `carried - shed_room` units that `DROP` would delete. If the selected executable market prefix already contains a positive SELL for that same item, the current market rows can remain byte-for-byte unchanged.

This is only a one-step state/evidence theorem. Retained pocket stock can affect later authored actions, so full-game value must be measured rather than inferred.

## Candidate boundary

`overflow_safe_drop.transform()` engages only when all of these are true:

- exact public `player in {0,1}` and nonnegative plain-int `step`;
- standard V5 board/shed/market-cap configuration (10 / 100 / 10);
- exactly one selected shed-affecting unit action, and it is `DROP`;
- actor is at one of the four shed-access tiles;
- actor carries exactly one positive stack;
- item is a non-operating sale good (`CARROT`, `TOMATO`, `STRAWBERRY`, `MELON`, `EGG`, `MILK`, `WOOL`); WHEAT/FERTILIZER are intentionally excluded;
- carried quantity exceeds current shed room;
- executable market prefix already contains a positive same-item SELL.

The transform never changes market rows, row order, other actors, quantities, route/controller state, config/defaults, package authority, archive bytes, or Kaggle submission bytes.

## Verification

Focused contracts use the canonical extracted `mechanics._apply_unit_action` to prove the immediate baseline DROP and candidate PLACE/PASS leave identical farm + shed state while the candidate retains exactly the baseline overflow in pocket. Additional predecessors cover multi-item pockets, operating inputs, malformed market rows, nonstandard config, multiple shed operations, hand actors, engine quantity coercion/trailing SELL fields, and exact public identity.

Requested checkout commands from this directory:

```bash
python -B -m unittest -v test_overflow_safe_drop.py
python -O -B -m unittest -v test_overflow_safe_drop.py
python -m py_compile overflow_safe_drop.py test_overflow_safe_drop.py
```

## Evaluation handoff

Before any production hook or config key is considered, census the current authored V5 routes/replays for selected `DROP` at shed access where the actor carries more than remaining room in exactly one supported sale good. For each witness, compare control vs this transform on identical candidate identity, opponent, seed and seat. Record engagement count, units preserved, later liquidation vs EOD deletion, final margin delta, and any later action whose effect changes because pocket stock survived. A dormant helper or a synthetic one-step proof is **not** promotion evidence.
