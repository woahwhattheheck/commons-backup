# ASTRA-SPAWNSTEER — deterministic HIRE spawn control

**Status:** source-bound research / default-OFF / no runtime or policy activation.

This is an additive sublane inside the existing canonical
`repairs/gameplay/redundant-hire-two-seat/` family. It does not add a second
scheduler, HIRE cadence, controller, V4 tree, configuration key, or gameplay
default.

## Source theorem

Official engine Git blob
`3c202c7ee921da239356789e266b694635103fc4` makes successful HIRE spawn
deterministic from **current** shed-corner occupancy:

1. The four shed access tiles are ordered NW, NE, SW, SE.
2. `_spawn_hand()` counts the farmer and every existing hand currently standing
   on those tiles.
3. It chooses minimum `(occupancy, NWSE index)`.
4. Unit actions run before the market phase. A same-callback MOVE therefore
   changes the occupancy seen by a later successful HIRE.
5. The new hand cannot take a unit action until a later callback.

This is the optimization counterpart to the older WIDEFIELD correctness
boundary: route edits before HIRE are not position-local because they can change
the newly hired hand's spawn.

A canonical minimum-cardinality occupancy certificate that forces target index
`j` while leaving the target empty is:

| target | occupancy NW,NE,SW,SE | existing actors required |
|---|---|---:|
| NW | `0,0,0,0` | 0 |
| NE | `1,0,0,0` | 1 |
| SW | `1,1,0,0` | 2 |
| SE | `1,1,1,0` | 3 |

So steering is mechanically real, but not automatically useful. Actors get only
one unit action per callback; a multi-tile reposition cannot be teleported into
the HIRE callback.

## Oracle

`spawn_steering_oracle.py` provides only deterministic source mechanics:

- exact Git-blob authentication for the official engine;
- engine-equivalent shed-corner order and occupancy selection;
- minimal forcing certificates;
- exact one-callback PASS/cardinal-move position updates, including
  out-of-bounds MOVE no-op behavior;
- a supplied-witness certificate reporting baseline vs steered spawn.

It deliberately refuses farm operations in the one-step movement witness rather
than silently assuming they are position-neutral. The report is
`decision_authority=false`.

## Admission boundary

A current-native consumer must separately prove all of the following before a
spawn change can become a candidate:

- the authored HIRE actually executes (funding + row budget);
- the steering MOVE/PASS substitution does not displace a required current
  action or break an incumbent route/rejoin obligation;
- worker identity/index semantics remain valid after the HIRE;
- the new spawn reduces a concrete later route cost or enables otherwise
  unreachable productive work;
- both-seat current-native economics are measured.

No HIRE may be added, removed, or retimed by this package. LABORFLOW retains
redundant-HIRE/productive-detour economics and WIDEFIELD keeps its HIRE-boundary
route-correctness authority.

## Local focused checks

```bash
python -B -m unittest -v test_spawn_steering_oracle.py
python -O -B -m unittest -v test_spawn_steering_oracle.py
python -m py_compile spawn_steering_oracle.py test_spawn_steering_oracle.py
```

Authoring result: 11/11 tests pass in normal Python and 11/11 under `-O`, plus
syntax compilation. Current-native reachability/economics are intentionally a
separate execution gate.
