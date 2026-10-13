# Official-evaluator default dependency recovery

This is tooling inside the sole `main:candidates/v4` integration workspace. It is not another agent, a successor V4 tree, or a production release. The old #12351 source is preserved here without executing its builder or modifying production package inputs.

## What was stranded

PR #12351 head `a5b0b09eba576aa0c1740f708f29aedf82bb634d` repaired the packaged official evaluator's absent default dependencies. Its exact source review passed, but the production builder change was held pending a matching canonical rebuild and a real four-default smoke. Main builder blob `05994d946885ff0fe2a2ce77439fd335174900aa` still omitted the dependencies when inspected during recovery.

The compact opponent requires the REAL historical `revenue/kaggriculture/20260907-offline-agent/main.py` with module-global `POLICY` and `agent`, blob `f76bfdaa442b63c2a35de829e52e006fc55f6049`. The old PR description's `official_agent.py` alias is obsolete and incorrect; the final patch already corrected it. Do not restore that bad alias.

## Exact donor custody

`donor/opponents.py` is unchanged source blob `d18a3472cb1ea0f809ce1cd8ab7e4018aac73534`. The original builder and packaging suite are preserved as `.py.txt` with unchanged bytes, blobs `cb95bce13e984581e90435216317c96f51e6304f` and `9c7aec7daf354750b5b7331fb702afa9e0db8aa2`. The text suffix prevents accidental execution/test discovery against the wrong source layout. Their original paths were `build_integrated.py` and `test_evaluator_default_packaging.py` under the cloud-execution-lab root. Source authorship and review history remain in #12351.

The complete old builder is evidence only: DO NOT copy it over the current production builder. Original release rebuild/consistency requirements remain unresolved by this staging tool.

## Usable isolated staging path

`stage_evaluator_defaults.py` reads a local checkout and creates only a fresh, private directory OUTSIDE that checkout. It checks the exact Git blob of every source before any output exists, then copies nine files: evaluator, loader and its historical alias, unchanged opponent registry, actual historical compact candidate, three pinned engine files, and engine LICENSE. It imports/runs none of that code, performs no network call, and does not execute any legacy r04 materializer. Existing output directories/files are never overwritten. Pin mismatches exit 2; update pins only after source review, not via a bypass flag.

Run in a cloud checkout with Python 3.9 or newer (tested with 3.13.5):

```sh
LAB="$PWD/revenue/kaggriculture/cloud-execution-lab"
TOOL="$LAB/candidates/v4/repairs/tooling/evaluator-defaults"
python "$TOOL/stage_evaluator_defaults.py" --lab "$LAB" --output /tmp/titan-evaluator-defaults-new
```

The output path must not exist and its parent must exist. `STAGING.json` is written last, records exact copied bytes/hashes, and includes a `smoke_argv_not_executed` argument list. That command uses the current lab's `main.py`, pinned engine cache and the evaluator's unchanged FOUR default opponents, with NO `--loader`, `--opponent` or `--prepare-engine` override. It requests only an eight-step wiring smoke, NOT a full-game economic panel. Execute it only in the existing authorized isolated runner. Candidate code is executable; staging does not sandbox later execution. The source checkout must remain available for the chosen current candidate and its dependencies.

A successful staging receipt means only byte/layout preparation. A later real smoke must report all four opponents and both seats complete; a separate full-game, paired opponent-diverse panel is required for economics. Do not label either staging tests or an eight-step smoke a V4 performance win.

## Validation performed

`py_compile` succeeded. `python -m unittest discover -s "$TOOL" -p 'test_stage_evaluator_defaults.py'` passed 25/25, as did `python -O -m unittest discover -s "$TOOL" -p 'test_stage_evaluator_defaults.py'`, on Python 3.13.5. Tests use synthetic files with fixture hashes and prove copying without execution, source-tree immutability, exact alias layout, refusal on missing/changed/oversized/symlinked sources, output-path protection, partial-write cleanup, and non-destructive concurrent output claims. They are NOT the original builder/render suite and NOT an official-engine/default-opponent smoke. The new tool/test server blob IDs match the locally tested bytes.

No production runtime/default/scoring source, workflow, release builder, archive, current manifest or Kaggle submission is changed by this recovery. Do not execute the legacy r04 materializer against the current production ABI.
