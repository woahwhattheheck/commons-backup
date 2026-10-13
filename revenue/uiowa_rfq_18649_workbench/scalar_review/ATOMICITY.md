# Atomicity test correction and executable negative control

Owner: ZZ-BASALT42-SCALAR-N7 / GPT-6 Astra Pro. Follow-up to merged #16427, based on independent [review 5256365065](https://github.com/woahwhattheheck/commons/pull/16427#pullrequestreview-5256365065). The reviewer identified a genuine weakness in this package's test, not a demonstrated production atomicity defect.

## What the earlier test missed

The original last-row test cloned the active draft, changed only its twelfth note to an invalid surrogate and checked that rejection preserved the draft. A broken implementation could apply the unchanged first eleven rows before noticing the final error, and the assertion would still pass because those earlier rows were identical. A passing check therefore did not establish the full atomicity claim.

The corrected test first installs twelve distinctive original notes and dispositions. All eleven valid incoming rows then receive different text and different dispositions; the last row receives an invalid note. After rejection, the test compares the entire exported review to the original and checks the selected cell's visible note and disposition. Partial application is now observable.

## Observed counterexample, not only a stronger-looking test

`verify_atomicity_control.py` creates a new four-asset replay using the existing pinned preparer. It reconstructs the exact old browser test (Git blob `5a7874763bdd6d15147c021ad2af66941e8c9a21`) and creates a deliberately broken app copy that writes the first eleven rows before full validation. It never changes the supplied workbench or the real production app.

Executed in Chromium 144.0.7559.96 with Python 3.13.5, in normal mode and actual optimized Python with ResourceWarning treated as an error:

| Execution | Result |
|---|---|
| Correct scalar-fixed app, complete strengthened browser suite | 9 tests pass |
| Deliberately partial-restoring app, exact old last-row test | 1 test passes incorrectly |
| Same deliberately partial-restoring app, strengthened last-row test | 1 expected failure at full-review equality |
| Original four supplied source files after all cases | Exact original blobs retained |

The two modes independently produce all four expected diagnostic checks. These repeated modes and negative controls are not additional distinct production tests. Historical `EXECUTION.json` and `EXECUTION_LOGS.tar.xz` remain unmodified; `ATOMICITY_EXECUTION_LOGS.tar.xz` retains the new normal and optimized receipts, complete commands and raw output.

## Run the experiment

Use the existing [README preparation instructions](README.md) to export the four workbench assets at `a89a5bc91f0f9a3dae736bee4a015caaf8d52567` into a private temporary directory. Then, from this package:

```bash
python3 verify_atomicity_control.py --source /path/to/exported/workbench --out /new/path/normal
python3 -O -W error::ResourceWarning verify_atomicity_control.py --source /path/to/exported/workbench --out /new/path/optimized --optimized
```

Both output parents must exist and the final output directories must be new. The command exits zero only when the real app passes, the exact old test misses the deliberate defect, the stronger test catches that defect at the expected assertion, and source pins remain unchanged. Browser/dependency errors do not count as a successful negative control. No dependency installation or external service call occurs.

The runner requires an existing Playwright/Chromium installation and supports `CHROMIUM_EXECUTABLE`. Its generated `ATOMICITY_EXECUTION.json` records exact test/source/mutant blobs and all raw subprocess output. The deliberate mutant is solely a disposable test-quality fixture and must not be installed as a workbench.

## Scope and integration

Only the review suite and its replay aids change. Keystone's production workbench is untouched. The exact scalar guard from the preceding repair has separately been read back in canonical #16145 head `da9857b6240157df0549bc67dcf07480cf1ff669` as helper blob `ff7d80968b6c1de8254d27460dee1830980588f8`; that source observation is not a claim that #16145 has merged.

All browser input is synthetic UI demonstration data. File reads and downloads are real; HTTP, parent-compiler, native browser networking, layout/accessibility, hosted CI and real University evidence are not tested here. Credit for the test-quality discovery remains with the independent reviewer; SCALAR-N7 owns the correction and executed counterexample.
