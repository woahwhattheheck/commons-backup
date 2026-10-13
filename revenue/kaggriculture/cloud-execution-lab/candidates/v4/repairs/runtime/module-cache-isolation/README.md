# TITAN V4 — module cache artifact isolation

**Status: LOCAL_VALIDATED / PUBLISH_BLOCKED.** This packet has not been posted to
Slack, committed to the remote, opened as a pull request, merged, or activated.
The session's discovered GitHub and Slack actions were read-only. The packet is
an additive contribution to the **one existing `main:candidates/v4` workspace**,
not a replacement V4, runtime controller, or production release.

## Implemented repair

The current native `titan_runtime.load()` caches completed modules by name and
resolved path. Two inconsistencies remain in the original function:

1. **Cache hits do not restore the requested public import binding.** Load A,
   load a relocated B under the same name, then request cached A. The return is
   A, but `sys.modules[name]` is still B. A following real `from name import ...`
   therefore reads B. A constructed two-source witness gets 29 instead of 11.
   The repair reinstates the completed A module on a cache hit, without
   executing it again or publishing an incomplete module.
2. **The cache key and Python import specification use different paths.** The
   key resolves symlinks, but the old import spec uses the unresolved alias.
   Retarget an alias between equal-size, equal-mtime sources and the alias's
   timestamp-valid bytecode can load A into B's cache entry. The repair uses the
   same resolved artifact path for both the key and import specification. The
   regression explicitly compiles the stale alias bytecode, so it also runs
   with Python `-B` and does not depend on incidental pycache writes.

The existing `BaseException` rollback, prior-module restoration, foreign-binding
identity check, no-cache behavior, and completed-module-only publication remain
intact. `RUNTIME-DELTA.diff` is the human-readable change; the supported consumer
is the authenticated **source composer**, not a whole-runtime replacement.

## Input and output custody

| Item | Identity |
|---|---|
| Observed current native runtime Git blob | `b952c9c228ecbde592bf3d2df01638677abb0d24` |
| Original `load()` SHA-256 | `ad25182f731fb8b31fc4855b55dd96cc4ead622d08c03986073f0c4fc84b3296` |
| Repaired `load()` SHA-256 | `e369b0de72ca4284784298b8749765c0c8b93814555b5b4bf67faa50ddeeec64` |
| Generated runtime Git blob on that exact input | `1517b27bbc3108990a0a252d4d8e1f69a07b6359` |
| Downloaded GitHub Actions artifact | `woahwhattheheck/commons`, artifact `10175943272` |
| Artifact ZIP SHA-256 | `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8` |
| Checked native archive SHA-256 | `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9` |
| Full official interpreter Git blob | `3c202c7ee921da239356789e266b694635103fc4` |

`compose_module_cache.py` authenticates the sole synchronous, undecorated,
top-level `load()` physical byte span. It preserves **every byte outside that
span**, so unrelated runtime edits do not have to be overwritten. Changed,
missing, duplicate, decorated, or asynchronous loaders are rejected. Reapplying
to the exact repaired method is idempotent. The CLI only writes fresh output
paths; same-path and existing-file writes fail.

Before importing executable native code, `run_native_module_cache.py` verifies
the exact archive, its pinned `SOURCE.json`, and all **109 mapped runtime files**.
The candidate differs only in `titan_runtime.py`; the other 108 mapped files and
`SOURCE.json` remain unchanged. It checks the files again after execution. Input
and output file identities are in the native `INPUTS.json` receipts.

## Executed evidence

| Gate | Result |
|---|---|
| Component suite, normal Python | 33 passed; 0 failures/errors/skips |
| Component suite, `python -O` | 33 passed; 0 failures/errors/skips |
| Deliberately broken loader variants | 10/10 assertion-rejected in each mode; 0 infrastructure errors |
| Unchanged mutation controls | Passed in both modes |
| Original native module-recovery suite | 3/3 on baseline and candidate, normal and `-O`: 12 passing executions |
| Actual native pressure-method relocation witness | Old module imports B; repaired module imports requested A, both modes |
| Whole native games | 16 complete games, 11,504 TITAN callbacks, 11,520 interpreter calls including initialization |
| Baseline/candidate parity | All raw action, full serialized state/environment, reward, and status hashes match |
| Fallbacks or incomplete game calls | 0 |
| Cross-mode parity | All four seed/seat cells match in both arms |

The game panel is two seeds (`9922999`, `17`), both seats, baseline/candidate,
normal/optimized Python, against the pinned **official starter**. Each complete
game runs 719 action callbacks for the configured 720-step episode. The actual
unchanged `main.py::agent`, original `TITAN-CONFIG.json`, and full official
interpreter execute in separate serial processes for every arm/cell. No action
padding, compaction, truncation, policy override, or enlarged deadline is used.
The native one-second budget and 0.01-second reserve remain unchanged.

The native relocation witness calls the actual
`TitanAgent._market_pressure_selected` method with the literal archived feature
configuration. Two relocated **same-byte** `sell_priority.py` modules prove the
wrong dependency identity in the old method and the corrected identity in the
repaired one. This is a source-binding witness, not an economic gain. The
separate constructed different-value modules demonstrate a changed import value.

`VALIDATION.json` indexes results and disclosed development corrections. The
`evidence/` directory contains original final logs, per-game JSON records,
streaming trace hashes, input identities, mutation failures, and summaries.
Partial/interrupted development runs are not included or counted.

## Reproduction

Run from this directory in an offline Python environment. The executed
interpreter was Python 3.13.5; Python 3.11 was not tested. Tests use only the
standard library plus the authenticated native artifact.

```sh
python -B test_module_cache.py
python -O -B test_module_cache.py
python -B check_module_cache_mutants.py --output /tmp/module-cache-mutants-new
```

The downloaded artifact contains
`checked-package/exports/titan-current.tar.gz`. Pass that exact file to the native
gate; do not substitute whichever archive happens to be current later.

```sh
python -B run_native_module_cache.py \
  --archive /path/to/checked-package/exports/titan-current.tar.gz \
  --output /tmp/module-cache-native-new
```

The default native command executes both modes and checks cross-mode equality.
For an execution environment with a per-command time limit, the two modes can
also be run separately with `--modes normal` and `--modes optimized`, using
separate fresh output directories. Those are the final runs preserved here;
`VALIDATION.json` additionally records the checked cross-mode equality.

## Consumption into the existing V4

The current native assembler should consume this method patch **once**, alongside
existing runtime-lifecycle and terminal-fallback work. Other methods are not
owned or replaced by this packet. A changed `load()` body requires an explicit
rebase rather than relaxing the source hash.

```sh
python -B compose_module_cache.py \
  --source /path/to/single-v4-scratch/titan_runtime.py \
  --output /path/to/fresh-output/titan_runtime.py \
  --receipt /path/to/fresh-output/module-cache-receipt.json
```

No production file, configuration/default, archive, old branch, workflow,
`CANONICAL.json`, or Kaggle submission is modified by this delivered packet.

## Boundaries

This validates the **b567 checked artifact**, not the whole evolving V4
composition or newer SELL-core source. It establishes source binding and
behavioral parity, **not** competitive profit, a runtime speedup, hosted Kaggle
compatibility, a Python 3.11 result, or a deadline guarantee.

The contract is serial dynamic loading. `sys.modules` is a global namespace;
this patch is not a thread-safe multi-package import system or a hermetic module
graph. It cannot rewrite already imported consumer references. Use a fresh
process after composition. In-place edits to a completed cached source are not
watched or automatically reloaded. For symlink/relative aliases, canonical
resolved `__file__` and `__spec__.origin` are intentional behavior. Native paths
already use a resolved package root.
