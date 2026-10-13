# Mortgage reconciliation execution record

Accepted execution date: **19 September 2026**. This record describes the completed local operator runs and separately credited independent tests. It does not rerun or replace their raw records. Frozen product code and accepted logs were unchanged while these delivery documents were written.

## Actual operator runs

The two actual top-level commands ran from `/workspace/scratch/02152e3a5897/trellis/revenue/lloyds_launch_2026_mortgage_case_reconcile`:

```sh
python -B rehearse_mortgage.py --output-dir /workspace/scratch/02152e3a5897/mortgage-rehearsal-normal-v1
python -B -O rehearse_mortgage.py --output-dir /workspace/scratch/02152e3a5897/mortgage-rehearsal-optimized-v1
```

Each completed with exit 0 and reported eight child commands. Child processes used `/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python`, `-B`, and, for the optimized run, an actual `-O` argument. The optimized record has `python_optimized: true`. These receipts do not constitute a Python-version compatibility matrix.

| Step in each mode | Normal exit | Optimized exit | Observed result |
|---|---:|---:|---|
| Create baseline packet | 0 | 0 | Exact original input bytes retained; five issues and ambiguous current milestone |
| Run baseline copied verifier from baseline directory | 0 | 0 | Packet recompiled and verified |
| Create revised packet | 0 | 0 | Separately supplied correction retained; zero issues, current milestone `REVIEW` |
| Run revised copied verifier from revised directory | 0 | 0 | Packet recompiled and verified |
| Compile baseline through original three-output interface | 0 | 0 | JSON, CSV and HTML each byte-equal to the corresponding baseline packet file |
| Verify separate baseline receipt against original input | 0 | 0 | Complete receipt matched recompilation |
| Verify a separate deliberately edited receipt | 2 | 2 | Current milestone had been changed to `REVIEW`; compilation mismatch rejected |
| Attempt another bundle at the existing baseline destination | 2 | 2 | Destination rejected; every original packet file unchanged |

The six successful commands in each mode returned `ok: true` and empty stderr. The edited-receipt command returned empty stdout and the error `receipt differs from a fresh compilation of the supplied case`. The existing-destination command returned empty stdout and an existing-destination filesystem error. The deliberately edited receipt is outside both valid packets.

Each run retains `rehearsal.json`, `READOUT.md`, and eight command JSON records plus separate raw stdout/stderr files under `commands/`. The command records include the literal argument vector, rendered command, working directory, actual and expected exit codes, stdout and stderr. Their absolute paths document the execution environment; use a new destination to reproduce elsewhere.

| Complete operator record | SHA256 |
|---|---|
| `mortgage-rehearsal-normal-v1/rehearsal.json` | `d04005c0eb42cd8dd9ad3685e0e9f15835d065e45bbecdcd448d06f76a13d383` |
| `mortgage-rehearsal-optimized-v1/rehearsal.json` | `c67a9b52bcc3a6b0bba2131ea456971d7f01f1b9ed0beb58e07266858e652f07` |

## Source and fixture identities

The operator records both bind these same source and input bytes. The Git blob IDs below identify the corresponding local file contents; repository publication supplies their commit context.

| File | Git blob | SHA256 |
|---|---|---|
| `mortgage_core.py` | `811add9edce0955428385294c540d3d25ce577a8` | `3e4fe6e51951e71043cc330217d5fd5e9a04fb5308760b281a4a740a7cd4b007` |
| `mortgage_case_reconcile.py` | `3a00835019b28ff86f1da76be1131d630a207566` | `56612fb21284e58a36e79911c2d3167c38e2488982d93da1e4f84942c02d0d28` |
| `rehearse_mortgage.py` | `e2caae84a725cdb7450acf53499cbbcaa7ad09f8` | `e9cfda648c48ab4e0ada6404259119e98689c92569967c63fcf926c1932ce5ec` |
| `sample_case.json` | `8a87eaad29857a0a95cb6f637b12a8c9afbeb50d` | `796e3c37b2a23d01cda855050efd37c13434aa5150a6d2a81a337fe53a131e54` |
| `revised_case.json` | `0d05019570af2e04d74801b00dbed0fd5f5c96f7` | `f929303f0104f7dd9e1d6ee0008817fb7c92a935698abcf1b09dfd47d37d4589` |

## Recorded case identities

| Identity | Baseline | Revised |
|---|---|---|
| `source_digest` | `e0d2616ac21c2521687c1e91e0d3fe83d0682303255e702c10541b84060a8db9` | `19af83b07a1e366d4899b8dddc5ab800fef36c77006d0b49333dfb7aaa371c99` |
| `semantic_digest` | `a7efaba1df2cbd029a8be33fdac50bc34f6a2484f347bd1dc463847d9fe7bbd9` | `ceb915578df4b9c1fa62267882e4fda1e0ac37589bccdac4fe2504bd6961a8ab` |

The baseline was `REVIEW_REQUIRED`, `current_milestone: null`, `current_milestone_status: AMBIGUOUS`, with five issues. The revision was `NO_DECLARED_BLOCKERS`, `current_milestone: REVIEW`, `current_milestone_status: KNOWN`, with no issues. All eight authority fields remained false. [WORKED_EXAMPLE.md](WORKED_EXAMPLE.md) explains the supplied facts and corrections.

## Eighteen corresponding packet files matched

After the accepted runs, the retained normal and optimized packet bytes were compared. All nine baseline files and all nine revised files were identical across modes: **18 corresponding files, zero differences**. This comparison concerns packet contents; the complete rehearsal records differ because their commands, paths and optimization flags differ. The following hashes identify the normal packet files that matched their optimized counterparts.

| Packet/file | SHA256 | Normal versus optimized |
|---|---|---|
| `baseline/README.md` | `1ccef7e4dc5598f3859257bf43859a03749556f6ea9452fe880398ba6e81f402` | Identical |
| `baseline/bundle-manifest.json` | `5288e32c42c7ba9f6e4501e5c3390b84892f7eb35b62c6b377db7650d6442db0` | Identical |
| `baseline/case.json` | `796e3c37b2a23d01cda855050efd37c13434aa5150a6d2a81a337fe53a131e54` | Identical |
| `baseline/exceptions.csv` | `d305b7e1b34a32cab2a279ed4547306b10771e65f2700bf2f013f8fc2505556a` | Identical |
| `baseline/mortgage_case_reconcile.py` | `56612fb21284e58a36e79911c2d3167c38e2488982d93da1e4f84942c02d0d28` | Identical |
| `baseline/mortgage_core.py` | `3e4fe6e51951e71043cc330217d5fd5e9a04fb5308760b281a4a740a7cd4b007` | Identical |
| `baseline/normalized-case.json` | `de2ad7869a6ac8f19003c307a3bfd15023d05d484484b826d1a928db37e982eb` | Identical |
| `baseline/receipt.json` | `3c6815e037a18352ea213f89371e223601f581bb9a8b3c1bb5e0d0b3008d82e2` | Identical |
| `baseline/summary.html` | `211a9caed636f75c4f6acc39841cc349fb2816d28899f525b6b214e90ddaad83` | Identical |
| `revised/README.md` | `1ccef7e4dc5598f3859257bf43859a03749556f6ea9452fe880398ba6e81f402` | Identical |
| `revised/bundle-manifest.json` | `f514a811c7556e9e7b4380f814f880078117e6ef94fd33b8269b987f21b66410` | Identical |
| `revised/case.json` | `f929303f0104f7dd9e1d6ee0008817fb7c92a935698abcf1b09dfd47d37d4589` | Identical |
| `revised/exceptions.csv` | `6d390660f124794fe4e785264138df2ba68f7a612537d4db186ac674842eed0c` | Identical |
| `revised/mortgage_case_reconcile.py` | `56612fb21284e58a36e79911c2d3167c38e2488982d93da1e4f84942c02d0d28` | Identical |
| `revised/mortgage_core.py` | `3e4fe6e51951e71043cc330217d5fd5e9a04fb5308760b281a4a740a7cd4b007` | Identical |
| `revised/normalized-case.json` | `00a75ea69126f729e467040d0d093703f4ddb97bf30ae08e8e73182f4bcc551d` | Identical |
| `revised/receipt.json` | `972f6e8ce948e21aa693f695868c026d91d4826853827ac5bc75f7bc05081358` | Identical |
| `revised/summary.html` | `90450227f1cb9d6a36fc9ab88c116cd9f9113c47c67c80681ea80ed0079e4ad3` | Identical |

The `case.json` files also matched the exact original fixture bytes in each run. Each packet has its own completion manifest; that manifest was written last. Hashes establish content identity and reproduction, not record authorship, document authenticity or real-world completeness.

## Independent tests and bounded source review

The independent reviewer retained **32 component tests under normal Python and 32 under real optimized Python**, plus the repository discovery bridge passing in both modes. Each bridge invokes the component suite; those passes are discovery/propagation evidence, not additional unique test cases. The source reviewer reported PASS for the core and facade with no defect requiring a change. [TEST_EXECUTION.md](TEST_EXECUTION.md) contains the four accepted literal logs, source identities and the review limits. These tests were accepted without rerunning them for this document.

The test suite blob was `0a655b90c781931e3241e32f15e321798cb4b28b`; the repository discovery bridge blob was `d993de622781fcd725a91943ba59cc0474b5dd57`. The core and facade identities match the operator source table above.

## Scope of this evidence

The operator proof covers actual local CLI execution, recompilation-based verification, documented rejection paths, input/output preservation and retained artifact equality. It does **not** claim browser rendering or interaction was executed, nor that hosted CI succeeded. Static HTML inspection and export checks are distinct from browser acceptance. A source review or this local execution record does not establish a hosted workflow result, repository integration status or a later changed-head result.

No live broker/lender APIs, customer records, external outreach, programme submission, document authentication, lending decision, payment or revenue were demonstrated. All committed cases are fictional, and supplied corrections are retained as a separate input rather than inferred by the implementation.
