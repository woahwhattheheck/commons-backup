# Native unit geometry: bounded immutable cache

ASTRA-SPATIAL-COST. One additive component for canonical `main`, not another V4 controller or runtime. Status: **source/component ready; not installed or promoted as end-to-end speed/strength evidence**.

## Change and composition

Native `mechanics._is_shed_adjacent` reconstructs a four-element set on every call. Cache the deterministic shed-corner geometry in a `frozenset`, with a 16-entry, type-sensitive LRU. `tuple(pos)` normalization and `_shed_access_tiles`' detached mutable-list API remain unchanged. No farm, observation, private state, actor, decision, configuration flag or episode enters the cache. The official board-size domain is the supported runtime input; arbitrary custom Python numeric objects or live monkeypatching of geometry are not a compatibility claim.

`compose_geometry.compose(source)` authenticates the exact two relevant definitions, rejects duplicated/moved definitions, name collisions and double application, and replaces only the membership function. Unrelated bytes, including another owner's scalar-pricing changes, survive exactly. It does not reset a newer mechanics module to an old whole-file snapshot. Apply only to explicit staging, after checking the current source and composition order; the CLI rejects an in-place path. No default, production file, archive, workflow or Kaggle submission is changed by this package.

## Exact inputs

The existing Actions artifact **10175943272** contains `checked-package/exports/titan-current.tar.gz`, SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. It has 110 members, including `SOURCE.json`; the embedded runtime map has 109 members. `RAW-EVIDENCE.json.gz.b64` retains both complete member maps and original execution reports.

Baseline mechanics blob: `044a4f9c0a4a44dde10ada57563238bcaf82075d` (also read back from live main during this task). Composed mechanics blob: `4a0cb3d01682a0cc9544ac176928ba02b16ea7fb`. Pinned official engine: `3c202c7ee921da239356789e266b694635103fc4`; the checker also authenticates its JSON specification and utils. Exact artifact runtime is b952; this is **not** a gate on every newer peer repair or the latest composed V4.

## Reproduction

Use Python 3.13 with the already available artifact; there is no new Actions dispatch or alternative game driver. Set `PACKAGE` to this component directory, `ARCHIVE` to the exact tar, and `BASE` to a fresh extraction of that tar.

```sh
python "$PACKAGE/compose_geometry.py" "$BASE/mechanics.py" /tmp/mechanics-geometry.py
python "$PACKAGE/check_geometry.py" --runtime "$BASE" --report normal.json
python -O "$PACKAGE/check_geometry.py" --runtime "$BASE" --report optimized.json
python "$PACKAGE/run_controls.py" --archive "$ARCHIVE" --output controls-normal.json
python -O "$PACKAGE/run_controls.py" --archive "$ARCHIVE" --output controls-driver-optimized.json
for mutant in missing_se_corner fixed_board_size lost_vector_normalization wrong_half_boundary mutable_geometry unbounded_cache; do
  python "$PACKAGE/check_geometry.py" --runtime "$BASE" --mutant "$mutant"
  python -O "$PACKAGE/check_geometry.py" --runtime "$BASE" --mutant "$mutant"
done
```

Each mutant run must exit 1 after eight tests; clean runs must exit 0. The vector-normalization mutant raises behavioral TypeErrors rather than assertion failures. Decode the original evidence without running game code:

```python
import base64, gzip, json
from pathlib import Path
raw = gzip.decompress(base64.b64decode(Path('RAW-EVIDENCE.json.gz.b64').read_bytes()))
Path('RAW-EVIDENCE.json').write_bytes(raw)
data = json.loads(raw)
```

## Executed evidence and limits

Eight tests pass in ordinary and optimized Python. **Per mode:** 50,540 exhaustive integer geometry comparisons plus vector-shape controls; 5,000 native unit-state comparisons against the actual official unit function; 216 paired full-interpreter synthetic transitions. The latter explicitly substitute only the geometry predicate for one arm and compare complete resulting states/environment. Six intentionally wrong semantic/cache variants are rejected in each mode. Source-custody, duplicate-definition, detached-list, immutability, capacity, bounds, actor and cache-size controls are included.

Two executions of the existing process-isolated evaluator each run four A/B pairs (seeds 2027/6607, both seats), totaling 16 complete games and 5,752 paired trace frames. All compared raw actions, post-turn cash trajectories, final observations and scores are identical; all 11,504 TITAN callbacks complete without fallback. This is not a comparison of every intermediate world-state field. Only staged `mechanics.py` differs; an identical evidence-only wrapper invokes the actual `main.agent` in both arms. Each candidate game records one geometry cache miss and 4,947 or 4,198 hits.

**Optimization-mode distinction:** the checker and microbenchmarks genuinely run both ordinary and `-O`. The second full-game repeat optimizes the evaluator's parent process, but its unchanged worker launcher uses a clean environment and plain `python -B -u`; native worker code is ordinary in both repeats. Do not call these optimized-native games.

Nine interleaved rounds per mode show approximately **61% less membership time** and **26–28% less actual native PICKUP/PLACE roundtrip time**. All individual timings and full-game resource measurements are retained. These are local microbenchmarks, not an end-to-end speed guarantee: the sampled native games make only about 4–5 thousand cached calls, and full-game timings are noisy. No leaderboard, competitive-opponent, improved cash, policy, activation, or complete-current-stack claim follows. The serializer should consume at most this one component after its own current-stack gate, not create another geometry implementation.
