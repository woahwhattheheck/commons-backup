# P07 current-HIRE existing-worker window — SOL-CROSSWIND

Operation: `titan-v3-p07-current-hire-existing-worker-window-20260910-01`

## Why this exists

The preserved P07 joint-actor candidate completed 384 official games with exact
paired score identity and **zero accepted live swaps**. Its implementation
returns `None` whenever the *current* selected row contains any `HIRE`, before
bundle extraction can inspect the actors or their routes.

The pinned official interpreter has the opposite ordering boundary needed for a
narrow safe repair: it executes the farmer and all currently present hands
first, then processes market orders. `_do_hire` appends a new hand and a new
inventory after those unit actions. A current-row HIRE therefore cannot
renumber an existing actor or cause a not-yet-created actor's current action to
execute.

## What changes

`current_hire_window.py` admits only the actor prefix physically present in the
observation. Current executable HIRE orders may coexist with that prefix;
future HIRE, checkpoint, and end-of-day rows remain hard cuts. HIRE in the
inactive market suffix, malformed rows, boolean/int aliases, and more extra hand
actions than current executable HIRE orders all fail closed.

`current_hire_joint_actors.py` delegates bundle extraction, route rebuilding,
collision checks, stock checks, application, and diagnostics to the exact
preserved P07 module. It changes only the window proof and binds candidate
workers to `range(existing_actor_count)`. The full market queue, every unit
outside the selected pair, and any action authored for a newly hired actor are
left byte-for-byte untouched.

## Evidence in this branch

- ten pure fail-closed window contracts;
- an official-engine AST/order theorem and append-semantics execution test;
- a predecessor discriminator: the old P07 rejects the same current-HIRE
  crossing fixture while the successor accepts it;
- an atomic preservation test for the market queue and the not-yet-created
  actor's full action tail;
- exact Git-blob pins for P07 source/results, the official engine, and
  `spatial_tempo.py`;
- deterministic one-tree port instructions with a new default-false feature.

Local pure-window result before publication: **10/10 PASS** under Python 3.13.
The full source-bound suite is executed by exact-head CI in the repository.

## Boundary

This branch does not mutate the canonical archive, runtime, configuration,
release pointers, provider state, games, or Kaggle submissions. It does not
claim a rating or playing-strength gain. Promotion requires live activation
and matched own-cash evidence; zero activation is a rejection, not a success.
