# Independent seed-repair composition controls

This is supporting evidence for the existing `repair_seed_funding_prefix.py`, not a second repair, strategy, runtime hook, or V4 integration line. The source owner is Slack claim `1789179343.204649`; this independent support owner is the later claim `1789179383.409289`.

## Executed result

Python 3.13.5: **13/13 tests passed normally and 13/13 with `-O`**. Each run covers 64 combinations of unrelated source text before/after the class, including Unicode, followed by 64 exact repeat applications. Further checks preserve inserted sibling methods, an independent operating-stock-method edit, and the order of an unrelated source edit. Drifted seed methods, duplicate direct targets, decorators, async methods, invalid input, and a modified postimage are rejected.

Eight deliberately broken composition functions are rejected in each mode: returning unchanged source; restoring a stale full-source snapshot; replacing text without authenticating the target; deleting final newlines; deleting non-ASCII peer bytes; rejecting a second application; accepting method drift; and introducing an unreviewed unbounded dependency scan. These mutants exist only in memory. No candidate file is modified by this runner.

The controls use an independent AST and byte-line locator rather than the repair's own locator. They assert exact equality of every byte outside the reviewed method. This tests source-composition safety, **not actual Git ref races**.

## Exact inputs and execution

The authoritative repair is Git blob `a5c2c131fd83d83d6be822556abce5723b464a50`; the entire runtime input is current blob `b952c9c228ecbde592bf3d2df01638677abb0d24` (33,885 bytes), recovered from existing GitHub artifact `10123395668`. This is not the older artifact's `a10ad66f` runtime. Both input hashes and the generated method hash are checked before the suite runs. Missing or changed inputs fail the run; they are never skipped or silently repinned.

From the repository root, after the existing source owner has landed the authoritative repair in this same directory:

```sh
P=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/runtime/seed-funding-prefix
export TITAN_CURRENT_RUNTIME="$PWD/revenue/kaggriculture/cloud-execution-lab/titan_runtime.py"
python "$P/run_seed_composition_controls.py"
python -O "$P/run_seed_composition_controls.py"
```

`TITAN_CURRENT_RUNTIME` may instead name an exact local copy of the pinned runtime. The default resolves the production root from this canonical package location. The runner emits JSON and exits 0 only when the baseline passes and all eight mutants are rejected; it exits 1 for a surviving mutant and 2 when the baseline evidence is invalid or failing. The supporting test module can also run directly with `python check_seed_prefix_composition.py`.

`COMPOSITION-RECEIPT.json` records both executed runs, source hashes, test/mutation counts, and SHA256 hashes of complete local stdout. It deliberately states that those raw stdout files are not separately preserved in Git; the numerical summaries and executable runner are preserved.

## Boundaries and deconfliction

Only the offline source transformer is executed. The resulting TitanAgent class is parsed/compiled but **never imported or instantiated** by these composition controls. There is no game, current-router, field-frequency, timing, or economic result here. No production file, feature default, release archive, or Kaggle submission changes.

The support author independently built a duplicate transformer before recovered Slack reads exposed the earlier claims. That local transformer and its overlapping gameplay tests were retired without publication. The existing source, market-control, and full-current-class owners retain those lanes. These four additions belong in the ONE existing canonical package; do not create another repair directory or restore retired source.
