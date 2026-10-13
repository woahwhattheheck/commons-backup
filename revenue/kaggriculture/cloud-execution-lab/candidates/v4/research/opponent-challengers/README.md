# Independent reactive challenger family (ORCHARD)

One benchmark-only component in the sole canonical `main:candidates/v4` workspace.
This is **one independent scheduler family with five profiles**, not five V4s,
not five independent algorithms, and not actual leaderboard opponents.

## What is built

`reactive_challengers.py` independently chooses production, feed procurement,
worker hiring, placement, watering, care, harvest, fertilizer collection, delivery,
and liquidation from each current observation. It imports no TITAN code, authored
action tapes, opponent private data, environment seed, network, or wall clock.
Calls carry no persistent episode state. Sheep, cow, goose, root-crop and mixed
production profiles share that explicit independent architecture.

Jobs reserve shared seeds, stock and serviced tiles in actual farmer/hand order.
New hires and purchases cannot act before the next callback. Procurement budgets
use observed cash rather than hypothetical sale receipts. Terminal cargo must
return to the shed: an end-of-day dump is not assumed at the partial final day.
This is a deliberately transparent baseline, not an optimal economic solver.

`OPPONENTS.json` is the machine-readable integration index. Import the module or
use the existing evaluator's `path.py::function` convention:

| Profile | Callable |
| --- | --- |
| dairy | `reactive_challengers.py::dairy` |
| poultry | `reactive_challengers.py::poultry` |
| fiber | `reactive_challengers.py::fiber` |
| roots | `reactive_challengers.py::roots` |
| mixed orchard | `reactive_challengers.py::agent` |

Riot retains the gauntlet orchestrator; SQUALL retains native sale-intervention
adversaries; COHORT retains the existing panel auditor. This package creates no
production controller, feature key, archive, workflow or Kaggle submission.
Keep its results separate from fixed traces and native-derived archetypes.

## Executed evidence

Python 3.13.5, normal and optimized modes. `VALIDATION.json` contains exact source
identities. `GAMES.csv` contains **all 52 declared panel games**, both terminal
cash rewards, source-family coordinates, unit-check counts and action/state
hashes. Earlier diagnostic repeats are excluded from this panel, not presented
as independent samples. `TEST-DETAILS.json.gz` preserves green controls and the
full assertion-failure logs for eight deliberately defective policies per mode.

* 26/26 focused tests in each mode, including an 80-cell legal-action matrix.
* Eight of eight behavioral faults rejected by assertions in each mode, with
  zero test errors. These are resource, input-aliasing, actor-count and order-cap
  faults, not merely syntax errors or source-hash mismatches.
* 52 complete games: 30 normal native games, two optimized native controls and
  20 starter controls. 37,440 full interpreter calls and 74,776 agent callbacks.
* All 23,008 native callbacks explicitly reported `completed`; zero unknown or
  fallback status. Every game reached the actual DONE transition at callback718.
* 222,314 projected unit actions matched the official unit interpreter; no
  mismatches or observation mutations. This checks the supported emitted subset,
  not arbitrary engine actions or equality of market forecasts.
* Both orchard seed17 normal/optimized game pairs match complete action-stream,
  observation-stream and terminal-state hashes, not just final scores.

### Strength result: useful diversity, currently soft opponents

The challengers beat the starter in **20/20** games and lost to the published
native archive in **32/32**. Native normal panel: seeds17/101/2027, both seats for
every profile. Source was frozen before the reserved101/2027 panel. Mean
challenger-minus-native margins across the six normal games per profile:

| Profile | Mean margin |
| --- | ---: |
| mixed orchard | -76,415 |
| dairy | -104,975 |
| poultry | -137,438.67 |
| fiber | -138,672 |
| roots | -147,364.33 |

Do not count these as five strong finalists, use their wins/losses as a promotion
threshold, or claim competitive V4 improvement. They add independently reactive
fixtures to expose structural regressions and support stronger future rivals.
No mechanism is declared dead because these particular challengers lose.

## Reproduce without network access

Obtain the already-existing checked package from artifact10175943272 and extract
its `checked-package/exports/titan-current.tar.gz` into a runtime directory. Archive
SHA256 is `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
The harness authenticates `SOURCE.json` plus all109 runtime members before calling
native `main.py::agent`. It pins the existing evaluator, loader and official
engine at `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c` rather than downloading code.

```sh
RUNTIME=/absolute/path/to/extracted/runtime
python test_reactive_challengers.py --runtime "$RUNTIME"
python -O test_reactive_challengers.py --runtime "$RUNTIME"
python check_mutants.py --runtime "$RUNTIME" --output mutation-results.json
python bench_challengers.py --runtime "$RUNTIME" --opponents native \
  --seeds 17,101,2027 --seats 0,1 --output native-results.json
python bench_challengers.py --runtime "$RUNTIME" --opponents starter \
  --seeds 17,101 --seats 0,1 --output starter-results.json
python -O bench_challengers.py --runtime "$RUNTIME" --profiles orchard \
  --opponents native --seeds 17 --seats 0,1 --output optimized-results.json
```

Each game runs in a fresh subprocess. A process failure aborts the panel, never
silently converts to PASS. Native diagnostic fallbacks are recorded separately;
a successful callback does not imply a completed native plan. The driver saves
completed rows incrementally. `--one --profiles orchard --opponents native
--seeds 17 --seats 0 --trace actions.jsonl` additionally captures every raw joint
action and post-observation hash. CSV hashes alone are not the full action bytes.

At most two local games overlapped during execution; no eight-worker stress was
used. Harness timings include its independent projector checks and are not a
production runtime speed claim. Per-process timeout is180seconds. The benchmark
compares the **unchanged published b567 archive**, not the still-unassembled V4
repair workspace. No Python3.11 or hosted Kaggle result is claimed. Adapting a
future native package requires an explicit new source pin and fresh validation.

Game constants and mechanics follow the Apache-2.0 Kaggle Kaggriculture source
at the pinned commit. This independently authored package is Apache-2.0.
