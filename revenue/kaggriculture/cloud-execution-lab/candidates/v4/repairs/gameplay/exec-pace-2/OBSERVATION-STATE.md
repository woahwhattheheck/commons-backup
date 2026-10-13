# EXEC-PACE-2: contiguous public-price evidence

## Disposition

One source-level repair in the existing canonical `main:candidates/v4/repairs/gameplay/exec-pace-2` package. The exact recovered donor remains untouched at `raw/r04_exec_adaptive.py` (Git blob `0ef551145dbcac9884e7d1710bcf11238dafc504`, SHA256 `637fe1810f2f937f13ce0407e15d5118e4b5db301cd3395f72654574d5189b83`). The package-root `r04_exec_adaptive.py` is its tested observation-state successor, not a second pacing strategy. It preserves the seven goods, 25-sample endpoint slope, threshold 0.03 and `reset/note_prices/slope/rising` API.

No router, materializer, key, default, production module, archive, evaluator, or Kaggle submission changes are included. This is **not** a current-runtime port or an economic promotion. Existing donor custody/wiring owners retain their surfaces; neither the original 15 focused tests nor their missing wiring bytes are reconstructed here.

## Reproduced predecessor defects

* Twenty-four missing quotes are inserted as zero; one subsequent real quote of 100 certifies a spurious slope of 100/24.
* A malformed step after a positive window leaves the old `rising=True` signal available.
* Twenty-five observations at steps 0,10,...,240 are treated as a 24-step rather than a discontinuous history. A one-dollar endpoint gain incorrectly exceeds 0.03 per step.
* An identical same-step callback erases a mature trend, contrary to the donor's documented idempotence.
* Player changes do not invalidate history, and nonfinite/coerced prices are admitted.

The repair requires positive literal-integer engine quotes and strict nonnegative integer steps / two-seat player identifiers. Invalid time/player/market clears all evidence. An invalid or missing individual quote clears only that good. Gaps, rewinds, player changes and conflicting duplicate callbacks restart warmup. Identical duplicate observations are idempotent. Input dictionaries are not mutated or retained.

Call `reset()` at known game boundaries. A public observer cannot distinguish every new game from a contiguous same-player continuation, and module-global state is not a substitute for runtime lifecycle ownership. Interleaved seats reset rather than mix histories. The production-port owner must provide per-game lifecycle custody before installation.

## Executed checks

Python 3.13.5 in this container, normal and `-O`:

* 24 observation-state tests, including 10,080 deterministic complete-window good/step/seat comparison cases: PASS in both modes.
* 8 pinned official-engine price-stream tests: PASS in both modes. Two starter-vs-starter episodes, two seeds, both public seats, 719 callbacks each, 2,876 observations and 20,132 good/window comparisons. Complete uninterrupted streams match the exact donor for both slope and rising decision; 13,484 comparisons are rising. This is price-detector coverage, **not** TITAN activation or game strength.
* Exact donor negative control: 38 assertion failures/subcases in the 24-test state suite and six assertion failures in the eight-test engine suite, in each mode.
* Eight compiled behavioral mutants rejected by assertion failures in each mode (16 executions). Missing dependencies/source drift cannot count as a mutation kill.
* All four Python additions compile normally and optimized.

The original subprocess-per-mutation development runner exceeded two outer execution time limits. The committed runner instead loads each isolated subject/test module in-process, restores the source-selection environment after each case, and was executed to completion normally and optimized. No timeout was counted as a mutation kill or a passing gate.

## Reproduce

From this directory:

```bash
python -m unittest -v test_observation_state
python -O -m unittest -v test_observation_state
python check_observation_mutations.py
python -O check_observation_mutations.py
```

For official-engine checks, supply already-present pinned source files (the existing GitHub artifact `10123395668`, run `34400824037`, carries them):

```bash
export EXEC_PACE_ENGINE_DIR=/path/to/final-pressure-runtime/checks/reference/engine
export EXEC_PACE_LOADER=/path/to/final-pressure-runtime/checks/reference/evaluator/loader.py
python test_observation_engine.py
python -O test_observation_engine.py
EXEC_PACE_SOURCE=raw/r04_exec_adaptive.py python -m unittest test_observation_state
EXEC_PACE_SOURCE=raw/r04_exec_adaptive.py python test_observation_engine.py
```

The final two commands deliberately fail and reproduce the predecessor defects. Repeat them with `python -O` for optimized controls. The engine runner authenticates all three engine files, the loader, and the original donor before importing the engine. It never downloads missing bytes. The artifact's runtime/archive freshness is irrelevant to this bounded source proof and is not asserted here.

Future integration must authenticate current call sites and prove key-OFF/returned-action equivalence, per-game state isolation, then opponent-diverse paired economics. Do not execute the legacy `apply_v4` against the modern frozen/ordered runtime or infer sale-timing profit from a positive observed slope.
