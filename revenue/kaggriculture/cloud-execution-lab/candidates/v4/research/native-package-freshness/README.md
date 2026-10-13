# Native package freshness gate

`check_native_freshness.py` closes one execution-evidence gap: an authenticated artifact may still be stale relative to the exact canonical checkout used to call it **current**.

The gate is read-only and policy-inert. It never builds, extracts, publishes, rewrites, activates, or promotes a TITAN package. `CURRENT` now binds the complete canonical publisher source map, not only a hand-picked runtime core:

1. require the canonical live root `revenue/kaggriculture/cloud-execution-lab`; caller-selected tracked decoys are invalid;
2. authenticate the supplied tar bytes and enforce compressed, member-count, per-member, and cumulative uncompressed-size ceilings;
3. bind `HEAD` and the live `build_integrated.py` publisher to the exact expected commit, and fail closed on any tracked worktree deletion before both publisher-map passes so dynamic source enumeration cannot self-consistently shrink under a fixed `HEAD`;
4. derive the canonical `source_files()` map with a structural AST interpreter that never executes tracked publisher code; the interpreter recognizes only the current read-only `RUNTIME`, mapping assignment, bounded `rglob` / `is_file` / `relative_to`, `str`, loops, comparisons, and comprehensions needed by the canonical publisher;
5. require authenticated packaged `SOURCE.json.runtime` to match that canonical map exactly;
6. require the tar member set to equal the mapped members plus `SOURCE.json`, with every runtime row's byte count and SHA-256 matching its member;
7. compare every mapped member against the exact expected-commit live source bytes, including publisher mappings that reach sibling source trees such as `../cloud-committed-seed-retry/...`; and
8. rederive the publisher map, reread every unique live source, and recheck `HEAD` before publishing the verdict.

The original five `CORE_PATHS` remain a mandatory minimum contract:

- `main.py`
- `titan_runtime.py`
- `scheduler.py`
- `frozen_selected.py`
- `TITAN-CONFIG.json`

They are no longer the coverage boundary. A package whose five core members match but whose mapped `spatial_tempo.py`, `terminal_history_join.py`, `early_capital.py`, reference source, or other publisher-mapped member is stale cannot be labeled `CURRENT`.

Any mapped package/live byte difference is `STALE`. Malformed or untrusted evidence, noncanonical live-root selection, publisher/source-map drift, undeclared or missing tar members, `SOURCE.json` metadata mismatch, dirty or mid-verification-mutated live bytes, symlinked live/package paths, duplicate tar members, archive hash drift, decompression-bound overflow, or commit drift is `INVALID`.

Example:

```bash
python check_native_freshness.py \
  --repo-root "$GITHUB_WORKSPACE" \
  --archive /tmp/titan-current.tar.gz \
  --expected-archive-sha256 <authenticated-tar-sha256> \
  --expected-commit "$(git rev-parse HEAD)"
```

Exit codes are `0=CURRENT`, `1=STALE`, and `2=INVALID`. JSON is deterministic and includes the package member, publisher `source_path`, and exact SHA-256 + Git-blob identities for both live and packaged bytes.

## Boundary

This is an execution-admission theorem, not a package publisher or gameplay mechanism. The active current-native refresh owner retains artifact construction/custody. FASTTAPE and other package families retain their own semantic rebinds. `COMPOSITION.json`, `INTEGRATION.json`, production runtime/default/config bytes, archives, and Kaggle surfaces are outside this package.

## Historical motivating witness

Authenticated artifact `10180428228` / tar `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9` has package core blobs `main.py=4a8cf7bc…`, `scheduler.py=a483b24d…`, `frozen_selected.py=fc7baf5c…`, `TITAN-CONFIG.json=3a3bef83…`, but `titan_runtime.py=b952c9c2…`. At construction base `44af4a1d…`, canonical live runtime is `6d9720f4…`; therefore that authenticated package is `STALE`, not current. The widened gate is general and does not special-case those identities.
