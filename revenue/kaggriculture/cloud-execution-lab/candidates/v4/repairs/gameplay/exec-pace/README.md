# r04_exec_pace — direction-conditional execution pacing (V4 lane, default OFF)

Microstructure lane. Measured **+$63/game mean (SE $7)** over the hardened
gate, GATED-PASS under stack-and-ship. Ships default OFF.

## Mechanism

Tracks a trailing 25-step observed-price history per drainable good
(WOOL/MILK/STRAWBERRY/MELON). When the trailing slope exceeds +$0.03/step the
good's market is momentum-rising (shop drains outpacing supply): dumping the
sale window's advanced quantity in one step walks the price down for no
reason, so per-step advanced/flush sales for that good are capped at
drain-absorbing levels (WOOL 3, MILK 3, STRAWBERRY 4, MELON 6), spreading the
same units across drain ticks to harvest the recovery between chunks. When
the market is flat/falling the window keeps its dump-early behavior (optimal
in glut regimes). Direction-conditional, so it is safe in both regimes.

Caps are applied inside `reserve_sales()` BEFORE debt recording: un-advanced
units stay planned at their tape steps — leak-free by construction (no
E1-style debt leak). The evening flush applies the same caps. Pacing stops at
`END_STEP` (690) so the endgame flush finishes unimpeded.

`r04_exec_pace.py` carries only observation state, the slope test, and the
caps. State is per-game (step <= last recorded step resets histories, fixing
the cross-game state leak that killed the drain-candidate gate). Every entry
point fails closed and never raises. Stdlib only.

## Gate evidence (hardened gate, 2026-09-12)

- Panel: 8 seeds x 2 seats x 2 variants x 3 replicates.
- Negative control (base-vs-base, n=4): mean -1, stdev 2.
- Main panel dM: mean **+$63**, SE **$7** (16 hardened cells; 2 unstable cells
  excluded per the harness rule).
- Verdict: GATED-PASS. Full log: `~/workspace/build/v4/gate-execpace-run.log`
  on the build machine (fleet artifact; not committed).

Relation to `repairs/gameplay/exec-pace-2`: that is a distinct successor
mechanism (`r04_exec_adaptive.py`, adaptive pacing). This lane is the original
direction-conditional mechanism (`r04_exec_pace.py`). Both are preserved;
the composer decides stacking vs supersede.

## Files

- `r04_exec_pace.py` — the lane module (standalone, stdlib only).
- `checks/test_v4_exec_pace.py` — 19 focused tests: slope detection,
  cap_for rising-only semantics, per-game state reset, router seams,
  key-ships-off, install toggling, never-raises on malformed input.
  The `RouterWiring` subset runs against the composed canonical router
  (it imports `r04_full_router`); receipts below were taken in the
  materialized carrier tree, the gated artifact.

## Test receipts (2026-09-12, Python 3.x)

- `python3 -m unittest checks.test_v4_exec_pace` → **19/19 OK**
- `python3 -O -m unittest checks.test_v4_exec_pace` → **19/19 OK**

## Composition wiring recipe (default OFF)

Exact edits the composer applies against the canonical v4 router baseline
(`candidates/v4/donor/overlay/r04_full_router.py` lineage), matching the
gated carrier:

1. `r04_full_router.py`
   - `import r04_exec_pace` (next to the other lane imports).
   - In `reserve_sales()`: `pace_cap = _exec_pace_cap(item, step)` before the
     reservation loop; `if pace_cap is not None and sum(a for _, a in reservations) >= pace_cap: break`.
   - `R04_EXEC_PACE = False` global plus `_exec_pace_cap(item, step)` helper
     (short-circuits to None when the key is off or `step >= r04_exec_pace.END_STEP`).
   - In `evening_flush()`: `quantity = min(quantity, pace_cap)` when the cap
     is not None.
   - In `_v3_stack()`: `r04_exec_pace.note_prices(observation)` as the first
     statement (records history; no-op on the action).
   - `install(..., exec_pace=None)`: `global R04_EXEC_PACE`;
     `if exec_pace is not None: R04_EXEC_PACE = bool(exec_pace)`.
2. `titan_runtime.py` (current-ABI runtime): `Features.r04_exec_pace: bool = False`;
   pass `exec_pace=bool(self.features.r04_exec_pace)` into `install(...)`;
   `self.diagnostics['exec_pace'] = bool(self.features.r04_exec_pace)`.
3. `TITAN-CONFIG.json`: `"r04_exec_pace": false` (ships OFF).

No runtime/default/archive/Kaggle activation is claimed by this PR; promotion
is the composer's step per the v4 serial merge queue.
