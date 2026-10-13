# UIOWA-095: generating a collection without replacing operator data

> Implementation status: the nondestructive generator recovery landed through [PR #16331](https://github.com/woahwhattheheck/commons/pull/16331). The workflow importer now checks its incomplete marker before reading a collection.

The collection is synthetic; its successful generation is not an assessment finding or a performance measurement. OP5-OBSIDIAN authored the retained benchmark and workloads. OP5-MARROW identified the existing-output deletion. ZZ–HALYARD-86 / GPT-6 Astra Pro implemented and executed this repair.

## Operator contract

`generate_collection.py --out PATH` requires a **new leaf directory**. It refuses an existing nonempty directory, an empty directory, a regular file, a directory symlink, a file symlink, or a dangling symlink. The program never recursively deletes output. Missing parent directories may be created. A relative path is relative to the current working directory; `--out .` is therefore refused.

Run from this component directory with a destination that does not yet exist:

```sh
python generate_collection.py --profile small --seed 20260919 --out /tmp/uiowa095-small-new
```

Exit 0 and the printed JSON summary establish that this invocation completed. An existing destination or an expected input/filesystem error produces exit 2, an explanation on stderr, and no success summary. Use a different new destination after either a successful earlier run or a failed run. Do not delete a directory merely to make a demo command succeed.

`benchmark.py --keep-workdir PATH` still uses a profile-named child directory per size. A repeated run must use a fresh work directory when those children already exist. Historical `results/` files and benchmark methodology remain retained; this repair does not change the benchmark's separate results-file overwrite behavior or recompute historical timings.

## Interrupted and failed generation

The generator first validates the workload and seed, reserves the new destination with exclusive directory creation, and creates an empty `.uiowa095-incomplete` directory. It removes that marker only after writing and summarizing the collection successfully. Failed and interrupted runs retain their output for inspection. The generator will not reuse that directory.

A marker means **incomplete invocation**, even when `manifest.json` exists. A late filesystem failure can occur after the manifest is written. Do not pass such a collection to the benchmark or another consumer. `workflow.import_collection()` now refuses a present marker (including a dangling marker symlink) before reading the manifest. The workflow CLI returns exit 2 with a diagnostic and no new report bundle. Other consumers must still check completion themselves; absence of the marker alone does not prove generation succeeded. An operator or orchestrator must observe successful completion before consumption.

This design prevents destructive retry behavior. It is not atomic multi-file publication, a transaction, an fsync/crash-durability guarantee, or protection against a process replacing ancestor directories concurrently. Parent-directory symlinks are not rejected. Keep the destination under a directory controlled by the operator; this is not a hostile multi-user filesystem defense.

## Workload compatibility

Successful default small, medium, and large collections preserve every original byte and every summary field at seed 20260919. The retained reference was generated from original source blob `6a21c5b6df263960c88bbc992d7bbfd78399bd4c`, not from the repaired implementation. The test suite reads the reference without updating it.

Custom workloads require a `Profile`, a nonblank name, positive integer counts for evidence/findings/recommendations/statements/documents and `big_doc_every`, and nonnegative integer body-line counts. Boolean, fractional, textual, or missing counts are rejected before creating output. A seed is an integer, not a boolean; negative integers remain supported. The minimal one-record profile with zero body lines is tested.

## Retained historical generator validation

The original 27 tests exercise actual filesystem objects and child Python processes, including three competing writers with exactly one winner, ordinary and optimized command-line execution, invalid inputs, retained symlinks, write failure, interruption, late failure, and immutable original-output parity. Only disposable synthetic sentinels are used. `VALIDATION.md` records the actual run and exact source objects.
