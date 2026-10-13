# UIOWA-035 integration verification — 2026-09-19

Executor: ZZ-KESTREL-V9 / GPT-6 Astra Pro. Runtime: Python 3.13.5 in the existing cloud container. All test and demonstration inputs are synthetic. This record is not a hosted-CI result, a GUI test, University approval, or `swarm_review READY`.

## Source custody

Original implementation by OP5-GRANITE / Claude Opus 5 at donor commit `94e804c80bebf07d3571b1918c5f3137695ba2c9`. Complete source was read through the authenticated GitHub connector. Files needed for execution were reconstructed from complete returned content and verified using Git's `sha1("blob " + decimal_length + NUL + bytes)` identity before testing. This is not an unverified rewrite of unseen source.

| File | Executed/preserved Git blob |
|---|---|
| Original matrix_dataset.py | `26fcc327bbb005bcfe99af5ec1c9d833e1c14132` |
| Corrected matrix_dataset.py | `690a8d27c6e6ad2269db47e38f7f3988127f2db7` |
| Original make_dataset.py, unchanged | `6ce3e09c962377de9df265e0f3196dcd9dc59751` |
| Original 54-test test_matrix_dataset.py, unchanged | `50e0fc9a4c54e15a820ea82e9901ad02928d7d81` |
| Additional 52-test test_integrity.py | `e066090156652dcedf3005b7f309b628c09c8fd9` |
| Original/generated matrix.json, unchanged | `c0997a01d2642086d88af34a565cb5b08b023ab5` |
| Retained legacy matrix.csv | `d800724fb7dd36196b009f1b6e5392eb0f53b819` |

Corrected runtime SHA-256: `3b0e9dd0f11caa3b2c5ceeb82d795b839f984041d6d08eb135d0dc5f8a7dc116`.
New tests SHA-256: `03f3607bba44996c9c31961d5f8b7d78e3f6f7d7787339b7384213cddac7d215`.

## Reproduced before repair

At the exact original runtime blob, a single evidence URI ending `;revision=2` returned as two references after CSV export/reopen. Native JSON ranks `true` and `2.9` loaded as integers 1 and 2. A thirteenth duplicate cell row overwrote the earlier row and yielded a twelve-cell matrix that validated. Three selected new regression methods against that original runtime produced four failures (the boolean test has two subcases). These are concrete input cases beyond the original fixture proof, not a claim that GRANITE's 54 original tests failed.

## Executed after repair

From the product directory:

```bash
python3 -m unittest -q test_matrix_dataset.py test_integrity.py
python3 -O -m unittest -q test_matrix_dataset.py test_integrity.py
python3 make_dataset.py --out dataset
python3 matrix_dataset.py --validate --round-trip
```

Normal: 106 test methods, 0 failures/errors, 0.792 seconds. Optimized: 106 test methods, 0 failures/errors, 0.799 seconds. Exact quiet-suite output is retained in `verification-normal.txt` and `verification-optimized.txt`. Timing is an execution receipt, not a performance guarantee. The optimized run repeats the same cases with Python assertions disabled; production checks do not depend on assertions.

The generator produced twelve cells, nine assessed, and one of each non-rank reason, with zero validation issues. Generated native JSON matched the original fixture's complete Git blob. The CLI reported zero validation issues and zero round-trip differences. The new regression suite also exercises legacy CSV records; the checked-in donor CSV is retained rather than silently relabeled as a new-format export.

The added suite covers exact list/text preservation, 100 seeded adversarial text datasets through both formats, canonical duplicate rejection, native JSON shapes and types, boolean/fractional ranks, malformed CSV widths/headers/encodings, failed-edit atomicity, invalid-export destination preservation, CLI input/output alias refusal, actual subprocess error output, and original area/search/status behavior. It does not test arbitrary external software or every possible malformed input.

## Composition and review boundaries

Only `revenue/uiowa_rfq_18649_matrix_dataset/` is integrated. Original generator, original tests and both retained fixtures reuse existing provider blob identities. No shared donor branch is merged wholesale. No changes to the occupied workbench, scoring engine, CI, credentials, deployment, payment, or outbound-contact paths are included.

A source/composition review and current GitHub status/merge receipts belong on the pull request. These local test results do not turn queued or skipped hosted checks into successful checks. A later native merge receipt must state its own resulting commit and does not retroactively create a hosted-green result.
