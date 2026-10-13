# Source-integrity and CLI controls

This additive support packet tests the one existing `repair_seed_funding_prefix.py`; it does not contain another transformer, runtime, installer, strategy or activation.

## Exact execution

CPython 3.13.5: **22/22 normal + 22/22 optimized**, zero failures/errors/skips. Seven deliberately broken source/CLI variants are rejected in each mode. `SOURCE-INTEGRITY-RECEIPT.json` binds the exact checker, mutation runner, owner transformer, complete input runtime and scratch output bytes. The input runtime was recovered from existing artifact 10123395668, not reconstructed from snippets. Both artifact runtime copies had the same b952c9c2 blob.

```sh
LAB=revenue/kaggriculture/cloud-execution-lab
P="$LAB/candidates/v4/repairs/runtime/seed-funding-prefix"
python "$P/check_seed_prefix_source_integrity.py" --runtime "$LAB/titan_runtime.py"
python -O "$P/check_seed_prefix_source_integrity.py" --runtime "$LAB/titan_runtime.py"
python "$P/check_seed_prefix_source_mutants.py" --runtime "$LAB/titan_runtime.py" --mode normal --output /tmp/seed-source-normal.json
python "$P/check_seed_prefix_source_mutants.py" --runtime "$LAB/titan_runtime.py" --mode optimized --output /tmp/seed-source-optimized.json
```

The whole-runtime and transformer pins intentionally fail on drift. Rebind evidence explicitly after review; do not silently accept a changed runtime. `--allow-mutant` is for deliberate negative controls only and does not disable runtime/method output assertions.

## Coverage and boundaries

The gate checks exact reviewed method bytes, unchanged bytes outside the method, repeat application, Unicode offsets, unrelated same-named methods/quoted method text, duplicate top-level classes/direct methods, decorated/async targets, method drift, all 14 partial combinations of the four changes, forged already-repaired input, newline authentication, syntax/UTF-8 rejection, and parsing without executing runtime source. CLI checks cover exact scratch output, existing-file refusal, same-path and symlink aliases, and no partial output after source rejection.

The mutation runner independently weakens duplicate-class/method/decorator guards, original/repaired source authentication, outside-method preservation, or exclusive scratch creation. A mutant counts as rejected only if the complete 22-test suite runs and fails; a parse error or no-tests run is not counted.

These are **source/CLI tests, not runtime behavior or economic tests**. The runtime source is parsed, never imported; no official engine or game is executed here. The peer method/market/full-class checks remain separate and must not inherit broader claims from this receipt. Production, defaults, archives and Kaggle are untouched.

## Retired donor

`ARCHIVED-11714-DISPOSITION.json` records the retrieved historical job's **4 failed / 17 passed**, including the cached post-unit fixture whose claimed baseline contrast was false. A correction was posted on PR #11714 (comment 5642895852). That branch remains donor history, not a competing V4 integration target; no old implementation was copied here.
