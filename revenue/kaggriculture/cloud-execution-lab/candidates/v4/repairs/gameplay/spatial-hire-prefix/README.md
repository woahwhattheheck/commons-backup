# SpatialTempo executable-HIRE boundary repair

One source-only component in `main:candidates/v4`, not another V4 runtime or controller.

## Mechanism and disposition

Current native `spatial_tempo.py` scans complete selected and authored future market vectors for `HIRE`. The official interpreter executes only a raw market prefix governed by `maxMarketOrdersPerTurn` (default 10). A HIRE in the inert suffix therefore blocks an otherwise certified weed-clearing BUILD/PLANT continuation even though no worker can spawn.

This exact-source transformer applies the executable prefix to both existing boundary scans. Empty/PASS/zero-sale slots still consume capacity: no filtering before slicing. Every executable HIRE remains a boundary. For authority safety, the transformer consumes `maxMarketOrdersPerTurn` only when it is a plain Python `int`; boolean, float, string or other malformed cap values fail closed by returning the inherited selected action without opening a SpatialTempo continuation. Missing cap still uses the documented integer default 10. Existing retry witnesses, seed/service checks, rejoin logic, emission and raw authored market vectors remain unchanged.

**Source-ready, not activated.** The pristine current native parent has four routes and 2,880 authored rows, with zero HIRE rows beyond the default raw cap of ten. The packet proves correctness on constructed/composed inputs, not natural engagement, final-game profit or playing strength. Do not activate merely because these tests pass. Production source, defaults, archives and Kaggle remain unchanged.

## Authenticated inputs

Use existing GitHub Actions artifact `10175943272` from `woahwhattheheck/commons`, not a newly dispatched run. Its ZIP SHA256 is `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`. The embedded `checked-package/exports/titan-current.tar.gz` is 429,604 bytes and SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.

Extract into a dedicated pristine directory. The runner authenticates SOURCE.json, all 109 runtime-map files and explicit engine/evaluator pins before importing package code. SOURCE.json SHA256: `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`. Exact official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

## Execute

From this component directory, first run the dependency-light strict-custody regression, then run the authenticated b567 suite:

```sh
python -B -m unittest -v test_strict_market_limit.py
python -O -B -m unittest -v test_strict_market_limit.py
python -m py_compile spatial_hire_prefix.py test_strict_market_limit.py test_spatial_hire_prefix.py

export TITAN_PACKAGE=/absolute/path/to/pristine-b567
python -B test_spatial_hire_prefix.py
python -O -B test_spatial_hire_prefix.py
python spatial_hire_prefix.py "$TITAN_PACKAGE/spatial_tempo.py" /separate/staging/spatial_tempo.py
```

The staging output must not exist. The transformer rejects source drift and repeated application, also under `-O`; it never patches production in place. If a peer has changed the source, recompose the two-scan semantics on that new source and rerun the evidence instead of relaxing the input pin or replacing their complete module.

To repeat the surrounding regressions, make two separate copies of the pristine package, replace only `spatial_tempo.py` in the candidate copy using the staged output, then run the following from each package root with normal Python and again with `python -O`:

```sh
PYTHONPATH=.:checks python -m unittest checks.test_weed_continuation checks.test_idle_fertilizer checks.test_crop_release checks.test_operating_stock checks.test_feed_stock -q
```

## Evidence generations

`RECEIPT.json` is immutable predecessor evidence for the original executable-prefix repair generation. It records nine focused tests per mode, 600 full official-interpreter callbacks per mode and five killed boundary mutants. It is retained as historical evidence and is not rewritten to describe the strict-cap successor.

`STRICT-AUTHORITY-RECEIPT.json` records the exact successor generation used by PR #13098. The dependency-light strict suite passes 4/4 in normal and optimized modes. The authenticated b567 suite passes **10/10 normal and 10/10 optimized**, executes 544 official-interpreter callbacks per mode, covers eight coercible-poison fail-closed cases per mode, and kills all six deliberate mutants including `coerce_type_poison`, which restores the removed `int(...)` coercion. The staged successor output is 55,733 bytes, Git blob `1c25a57e7533f012061ab1a3797a02c43b6c89cb`, SHA256 `aee3c482c521f0575b72c5e345028e9af4604f95e7378c5849a311ac8c68c9ef`.

The surrounding 118-test run yields **117 passes and the same one existing failure** for pristine and candidate packages, in both normal and optimized modes. The failure is `IdleFertilizerRuntimeTests.test_prelude_fallback_returns_and_sells_already_collected_unit`: prelude fallback returns PASS instead of SOUTH. This is identical across all four arms and belongs to the existing terminal-fallback lane; the strict-cap successor introduces no new surrounding regression.

## Single-tree handoff

The sole current-runtime assembler may consume this component only after composing with newer source and retaining package/fallback/competitive gates. `MANIFEST.json` binds the current successor transformer/tests/README and strict receipt while preserving the predecessor receipt as historical evidence. Do not execute a legacy V4 materializer, change a default, or replace another spatial/idle-fertilizer/crop continuation. No sibling controller or second V4 is authorized by this package.
