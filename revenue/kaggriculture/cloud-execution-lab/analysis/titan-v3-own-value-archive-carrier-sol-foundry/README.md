# TITAN V3 own-value archive carrier (SOL-FOUNDRY)

Operation: `TITAN-PR11899-ARCHIVE-CLOSURE-CARRIER-20260909-01`

## Why this exists

The exact-head hosted run for PR #11899 cleared its own source-binding checks, then
failed every canonical-control cell at step 0 because raw
`cloud-execution-lab/main.py` cannot import `observed_clone`.  That module is not
owned by the raw lab directory: `build_integrated.source_files()` maps it from
`../cloud-runtime-pulse/observed_clone.py` into the root of the standalone
current archive.  A one-module `PYTHONPATH` repair would be incomplete because
that source map owns several external root modules.

This packet executes both experiment arms from the same verified
`exports/titan-current.tar.gz` closure instead:

- **control**: the archive's untouched `main.py::agent`;
- **candidate**: the same archive closure plus a generated entry shim that
  installs PR #11899's reviewed `own_value_objective.py` overlay before importing
  the archive's canonical `main.py`.

No archive member is rewritten.  The generated arm roots are outside the Git
checkout and the candidate's only additional policy code is the exact overlay
file supplied on the command line.

## Fail-closed custody

`archive_carrier.py materialize` validates all of the following before publishing
an output directory atomically:

1. the canonical `CURRENT-ARCHIVE.json` path and strict JSON shape;
2. archive byte count and SHA-256 from that pointer;
3. regular-file-only, duplicate-free, traversal-free, sorted tar membership
   under bounded compressed/uncompressed sizes;
4. `SOURCE.json` identity against both the pointer and repository
   `CURRENT-SOURCE.json`;
5. exact member set, byte count, and SHA-256 for every runtime record;
6. identical canonical runtime-tree digests for control and candidate;
7. generated entrypoint, guard, and overlay hashes in `CARRIER-RECEIPT.json`.

Each evaluator worker then revalidates the complete runtime file set before any
policy import, rejects undeclared extra files and foreign same-named modules,
and proves that `observed_clone`, `scheduler`, `selected_sell_core`,
`titan_runtime`, and `main` all resolve inside that worker's private arm root.
The post-panel binder requires the evaluator's entry-file SHA-256 fingerprints
to equal the generated receipt.

## Run the focused contracts

```bash
cd revenue/kaggriculture/cloud-execution-lab/analysis/titan-v3-own-value-archive-carrier-sol-foundry
PYTHONDONTWRITEBYTECODE=1 python -m py_compile \
  archive_runtime_guard.py archive_carrier.py verify_panel_binding.py \
  test_archive_carrier.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v test_archive_carrier.py
```

The suite includes a predecessor discriminator: a raw `main.py` import without
its mapped root module fails on `observed_clone`, while both archive-backed arms
load it from their own arena.  It also attacks archive/pointer/source drift,
non-finite and duplicate JSON, bool/int confusion, path traversal, links,
duplicate members, runtime and overlay tampering, injected files, partial
publication, incomplete panels, and evaluator-entry fingerprint drift.

## Materialize and probe the real current archive

```bash
LAB=revenue/kaggriculture/cloud-execution-lab
PARENT="$LAB/analysis/titan-v3-own-value-objective-sol-objective"
CASE="$LAB/analysis/titan-v3-own-value-archive-carrier-sol-foundry"
OUT=/tmp/titan-own-value-carrier

python "$LAB/build_integrated.py" --check
python "$CASE/archive_carrier.py" materialize \
  --lab-root "$LAB" \
  --pointer "$LAB/runtime/integrated-selected/CURRENT-ARCHIVE.json" \
  --overlay "$PARENT/own_value_objective.py" \
  --output "$OUT" \
  --git-head "$(git rev-parse HEAD)"
python "$CASE/archive_carrier.py" probe \
  --entry "$OUT/control/control_entry.py"
python "$CASE/archive_carrier.py" probe \
  --entry "$OUT/candidate/candidate_entry.py"
```

The dedicated helper workflow deliberately stops after those exact current-archive
materialization and fresh-process probes, then re-inventories both roots.  It does
not duplicate the earlier carrier owner's 32-cell panel.  That owner can consume
the generated entrypoints and call `verify_panel_binding.py` before the existing
comparison step.

## Evidence boundary

This is an execution-closure repair.  It does not change the own-value objective,
SELL mechanics, opponent/seed/seat grid, comparator semantics, canonical source,
configuration, archive, release pointer, provider state, or Kaggle submission.
A green carrier proves that the experiment reached gameplay on bound bytes; it
is not by itself a score, promotion, or leaderboard claim.
