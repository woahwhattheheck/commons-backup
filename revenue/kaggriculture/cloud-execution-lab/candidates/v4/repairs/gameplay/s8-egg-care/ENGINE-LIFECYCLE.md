# S8 independent engine lifecycle controls

ASTRA-GOOSE delivery in the existing single V4 S8 family. GOSLING owns the repaired
policy; HENHOUSE owns native field economics. This is an executable engine oracle,
not another policy, native composer, default change, or promotion receipt.

## Run

Use the extracted `final-pressure-runtime` from artifact 10175943272. Only its
three pinned upstream files and exact offline loader are used; no network fetch,
Kaggle credentials, paid compute, or production edits are needed.

```sh
python engine_lifecycle_controls.py --runtime /path/to/final-pressure-runtime --output /tmp/s8-engine.json --mutations
python -O engine_lifecycle_controls.py --runtime /path/to/final-pressure-runtime --output /tmp/s8-engine-O.json --mutations
```

The CLI verifies upstream Git blobs and the loader SHA256 before execution.
It exits nonzero for any failed baseline control, skip, or surviving semantic
mutant. Mutation controls modify only an in-memory copy of the checked engine;
all positive/economic results use the unmodified complete interpreter.
`ENGINE-LIFECYCLE-VALIDATION.json` records both executed modes, exact source pins,
compact results, and SHA256 of each full generated receipt. The full receipts
include constructed state snapshots and action/state trace digests; rerun the
commands to regenerate them. Python version is included in each receipt.

## Executed

20/20 tests normal and 20/20 with `-O`; zero failures/errors/skips. All ten
semantic mutants are rejected by assertions in each mode, with zero test errors.
Each baseline suite includes 84 animal interval cases, 100 goose cap cases,
ten matched both-seat economic pairs, and a 124-transition legal initializer
trajectory through BUY/BUILD/PICKUP/PLACE/FEED/CARE/HARVEST/DROP/SELL.

| Constructed CARE minus COLLECT trajectory | Seat 0 cash delta | Seat 1 cash delta |
| --- | ---: | ---: |
| Collected fertilizer actually admitted and later sold | -50 | -50 |
| Collected fertilizer genuinely discarded, future egg admitted | +50 | +50 |
| Shed full at entry but same-turn SELL frees room | -50 | -50 |
| No next-day FEED | 0 | 0 |
| Extra future egg clipped by shed capacity | 0 | 0 |

These are actual interpreter fills and terminal money under matched scripted
continuations, NOT natural native-game profitability or an optimized comparison.
No repaired GOSLING source is executed by this receipt. The 124-transition legal
setup is not a complete game. This delivery reports zero native field games.

## Integration constraints for the same S8 component

CARE consumes no inventory. Its cost in S8 is the COLLECT_FERTILIZER action it
replaces. Current-day care is banked after current-day production; it does not
add an egg at that same EOD. A previously banked bonus is paid only on a fed
production day and is erased on an unfed production day. Bonus units clipped
by the animal-held cap are consumed, not carried forward.

A full shed at callback entry is not proof of discard: unit actions execute,
then the raw market queue, then EOD inventory drops. A same-turn sale may free
space; a purchase may fill it. Inventories drop in actor order. Replacing an
admitted fertilizer unit can also let another actor's egg enter the shed.
Therefore zero retained fertilizer cost does not by itself prove extra cash:
next-day feed, animal headroom, actual harvest, future shed admission, and a real
sale must also be witnessed. H3c HARVEST-before-refresh frees headroom and must
not be replaced by this test infrastructure.

Day27 CARE can pay at the day28 EOD and be harvested/sold on day29. Day28 CARE
cannot pay before the last executable callback718 under episodeSteps720.
The harness follows interpreter DONE and rejects attempted post-DONE calls.

## Reuse

Import `load_engine(runtime)` for the verified engine and provenance;
`World(engine, seat=..., day=..., ...)` for an explicitly constructed cut;
`World.tick(action)`, `until(step)`, and `terminal()` for complete transitions;
`paired_sale(...)` for matched actual-fill accounting. Do not install World or
these scripts into the native action path. Current policy/composer ownership
and feature activation remain unchanged.
