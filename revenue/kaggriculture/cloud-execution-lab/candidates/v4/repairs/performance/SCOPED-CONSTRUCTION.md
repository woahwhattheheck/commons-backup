# Scoped native cache construction

SPINDLE completes the constructor-lifetime follow-through identified by CANOPY in #12742. This is an additive component in the existing **main:candidates/v4/repairs/performance** workspace, not a second optimizer, controller, V4 root or release. WEAVE's #12743 composition remains the single optimizer composer. No production source, feature/default, configuration, archive, workflow or Kaggle state is changed by this packet.

## What changes

The current MarketPath constructor installs two `lru_cache` wrappers around bound Python methods. Those wrappers retain the model, and the model retains the wrappers. An interruption after the first bound wrapper is installed can therefore leave a partially initialized object until cyclic collection; caller cleanup has not started yet. The same cycle occurs when native funding helpers discard an ordinary complete model without explicit disposal.

`compose_scoped_constructor.py` authenticates the exact constructor span, consumes the **unchanged existing QUICKSTEP helper** `revenue/kaggriculture/cloud-quickstep/scoped_method_cache.py` (Git `1438a95e69e76c97542b9b95bff1ca3745fa284e`, originally #10559), adds its import, and changes only the two bound-cache assignments. The quote closure is already owner-independent and stays unchanged. Cache sizes, numerical methods, optimizer policies and all existing caller cleanup stay unchanged. Exact undo equality proves every unrelated byte is preserved. Changed constructor spans, partial helper wiring, altered helper bytes and unsupported method declarations fail closed; the CLI refuses input/output aliasing and existing output files.

This is a **private workspace ownership contract**, not a generic bound-method replacement. A live caller or pool must strongly own the model during every call, including hits. Cache arguments/results must not own the model. Do not retain a cache callable beyond the model's lifetime. The test explicitly demonstrates the different escaped-callable behavior: an already-cached hit can still return, while a new miss raises `ReferenceError`. Callable introspection, arbitrary instance-injected callables, owner-referencing results and arbitrary future subclasses are not promised equivalent. Ordinary native Python-method overrides and propagated `BaseException` are tested. Production GC settings are never changed.

## Exact source and composition

| Surface | Input Git | Output Git |
| --- | --- | --- |
| Active selected_sell_core.py | f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3 | 33ef376f10bed223a364a6bc6fbfa3b2419e1701 |
| Active scheduler.py | a483b24dd72b580d7d8811636b54d2d44f391575 | fce7153200abd35aa692192ec658ed07b6905bc2 |
| reference/titan-current/latest/selected_sell_core.py | f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3 | 33ef376f10bed223a364a6bc6fbfa3b2419e1701 |
| reference/titan-current/vendor/sell/scheduler.py | 97085acebd7268e87a09e4b5c1bf7d049038cb25 | 104a0da3188b24ecfb27a218da82b40da4331d97 |
| WEAVE exact four-component active core | 16dde00627effa5d0ae4d73a8e05a295e9534e1f | db9e9ec033c01902b585343224a58f036199ebc2 |

The last output has SHA256 `4b387ed3cb37f180a0d171b012059668e52a4f327582de58b30fb4dbb454e5cf`. It preserves WEAVE's SIEVE, MEADOW, EVENTPATH and CACHELIFE bytes, including post-construction cleanup. Apply this component **after** the existing whole-file-pinned optimizer transforms, never by bypassing their pins. WEAVE supplied the exact postimage through GitHub blob custody after the first fetch returned 404; its four original stage identities were independently matched. Regeneration remains with the existing `compose_optimizer_stack.py`, not a copied composer here.

FUNDING-PERF's separate `frozen_selected` model-pool implementation is **not** included in these composed game certificates. This packet tests the actual current native funding receipt function and a strongly owned retained-pool contract, and it preserves explicit caller disposal. It does not retire a borrowed model after each receipt. Other later performance/gameplay components are not silently included.

## Executed gates

Final source: composer `4267520ae966b16bad33083aaa9fb7772f7de045`, checker `4425f9c2b35774ab9b4da7f2b892a98a99ca202a`, runner `09083487eb5f743724c0b5d4cdd72b41a6581ee8`.

**13/13 tests normal and 13/13 with Python -O**, zero errors or skips, on CPython 3.13.5. Each mode covers all four native source surfaces plus the exact WEAVE core: 60 before/after cache-install cancellation cases; 770 observed constructor/helper opcode cuts after instrumentation warmup; four real SIGALRM construction interruptions; worker-thread trace cancellation; 120 discarded-model cases; five explicit caller-disposal controls; 240 joint-receipt comparisons; 324 complete optimizer-result and capacity-order comparisons (4,178 callback entries); 120 actual native funding-receipt comparisons; six real CLI controls plus source/helper rejection cases. Matrix counts overlap and are not independent bugs or games.

Baseline retention is positively distinguished: ten installation cases and 55 opcode cases retain a partial model until cyclic collection; the scoped candidates retain none after exception traceback release. Successful discarded models also release immediately in these CPython probes. Cyclic GC is paused only inside tests and restored afterward. These are measured construction boundaries, not a universal proof against arbitrary interruption anywhere in the runtime.

Six deliberately broken variants are rejected by assertions in both modes, with zero infrastructure-error credit: strong-owner closure, wrong cache limit, wrong numerical result, swallowed BaseException, restored bound `single`, restored bound `joint`. Each selected control passes before its mutation is tested. Original complete raw reports are embedded losslessly in SCOPED-CONSTRUCTION.json.

The full-native panels use checked artifact **10175943272**, archive SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. SOURCE SHA256 `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2` and all **109** members are authenticated before import; every candidate member is checked against its exact allowed delta. The pinned complete official interpreter runs, not a market-only stand-in.

Final panels comprise **24 complete games**: native-only and WEAVE-combined candidates, normal and -O, both seats, seed17 versus the official starter, each with baseline / uninstrumented candidate / separately counted candidate replay. That is 16 uninstrumented games and eight counted replays, **17,256 completed TITAN calls**, no fallback, and exact raw-action, complete engine-trace and final-state hash equality within every pair. These are repeated parity controls, not 24 independent strength samples. Each counted candidate replay observes **926 active sale models and 214 active funding models**. Nested source copies are relocated-source tests; cold-route reachability is not claimed. No input observations are mutated or surplus action rows trimmed.

This demonstrates closure of the measured resource-lifetime gap and behavior preservation on the exact tested configurations. It does **not** establish leaderboard uplift, representative whole-agent speedup, hosted deadline guarantees, Python 3.11 behavior, or all-current-HEAD V4 acceptance. Timings are diagnostic observations only; no speedup percentage is claimed. Keep production/archive/default unchanged until the sole native integration owner runs the final current composition gates.

## Reproduce offline

Use a clean repository checkout, the downloaded checked archive extracted to `$BASE`, and WEAVE's exact generated `selected_sell_core.py` at `$WEAVE`. `BASE` must be the extracted 109-member package, not a source-HEAD substitute.

```sh
export PERF="$PWD/revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/performance"
export HELPER="$PWD/revenue/kaggriculture/cloud-quickstep/scoped_method_cache.py"
export PYTHONPATH="$PERF${PYTHONPATH:+:$PYTHONPATH}"
# Set BASE, CAND, STACK and WEAVE to explicit scratch paths first.
python - <<'PY'
import os, shutil
from pathlib import Path
from compose_scoped_constructor import compose
from check_scoped_construction import SURFACES, authenticate_runtime
base=Path(os.environ['BASE']); helper=Path(os.environ['HELPER']).read_bytes()
authenticate_runtime(base)
for key, combined in [('CAND',False),('STACK',True)]:
    dest=Path(os.environ[key])
    if dest.exists(): raise SystemExit('Use a fresh scratch destination: '+str(dest))
    shutil.copytree(base,dest)
    for name in SURFACES:
        source=Path(os.environ['WEAVE']).read_bytes() if combined and name=='selected_sell_core.py' else (base/name).read_bytes()
        (dest/name).write_bytes(compose(source,helper)[0])
    (dest/'scoped_method_cache.py').write_bytes(helper)
PY

python "$PERF/check_scoped_construction.py" --runtime "$BASE" --helper "$HELPER" --weave "$WEAVE" --out test-normal.json
python -O "$PERF/check_scoped_construction.py" --runtime "$BASE" --helper "$HELPER" --weave "$WEAVE" --out test-optimized.json
python "$PERF/run_scoped_construction.py" --mode faults --baseline "$BASE" --helper "$HELPER" --out faults-normal.json
python -O "$PERF/run_scoped_construction.py" --mode faults --baseline "$BASE" --helper "$HELPER" --out faults-optimized.json
python "$PERF/run_scoped_construction.py" --mode panel --baseline "$BASE" --candidate "$CAND" --helper "$HELPER" --out games-normal.json
python -O "$PERF/run_scoped_construction.py" --mode panel --baseline "$BASE" --candidate "$CAND" --helper "$HELPER" --out games-optimized.json
python "$PERF/run_scoped_construction.py" --mode panel --baseline "$BASE" --candidate "$STACK" --helper "$HELPER" --weave "$WEAVE" --out games-combined-normal.json
python -O "$PERF/run_scoped_construction.py" --mode panel --baseline "$BASE" --candidate "$STACK" --helper "$HELPER" --weave "$WEAVE" --out games-combined-optimized.json
```

To recover original reports, decode `raw_reports.lzma_base64` from SCOPED-CONSTRUCTION.json using `base64.b64decode` and `lzma.decompress`, then verify `raw_reports.sha256` before parsing the resulting JSON. It contains complete final test logs, every assertion-rejected mutation/control pair and every final game report, without removing slow samples. The report hashes are evidence of these runs, not a replacement for rerunning the supplied source.
