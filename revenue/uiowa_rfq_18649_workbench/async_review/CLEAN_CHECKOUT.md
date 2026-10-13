# Clean-checkout preparation verification

ASYNC14-U8 / September 19, 2026. This corrects a packaging defect found during review of this carrier: the first preparation test version expected `fixed_app.js` and `saved_draft_utf8.patch` generated in the author's working directory. Those files were not committed, so a clean test invocation would fail before testing the real patch.

The fixture generator is now import-safe and exposes pure `derive(raw)`. The preparation suite derives the known reference bytes in memory, compares the retained production patch, and applies it only inside a fresh temporary directory. Both original and expected repaired application blobs are independently pinned. No expected digest is regenerated to fit a result.

Executed on a temporary copy containing **only** these five checked-in inputs: `composed_app.js`, `saved_draft_complete.patch`, `make_saved_draft_fix.py`, `prepare_native_fixture_patch.py`, `test_patch_preparation.py`.

```text
python -m unittest -v test_patch_preparation.py
Ran 6 tests in 0.046s
OK

python -O -m unittest -v test_patch_preparation.py
Ran 6 tests in 0.028s
OK
```

After both runs, neither `fixed_app.js` nor `saved_draft_utf8.patch` existed in that copy. This is an actual clean-input normal/optimized run, not the full workbench/compiler suite. Git blob identities: generator `f7d10efe12c83b551d618ef93290a846f9907d57`; preparation test `c17f3beabb5c47496d9ce6545b286e31e09b6179`.

The explicit CLI generator remains available for the before/after browser exercise. It writes UTF-8 bytes, verifies the expected fixed-app blob, and refuses existing output files, including symlinks. Use a fresh scratch directory, or `--output-dir` pointing to a fresh destination. Importing the generator never writes files. The browser runner and historical five-run execution archive are unchanged by this correction.
