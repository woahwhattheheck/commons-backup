# UIOWA-114: complete independent execution of the composed export repair

**ZZ-Lattice / GPT-6 Astra Pro.** Operation `uiowa114-export-lattice-20260919`.

This addendum supersedes the *pending original-suite execution* note in `EXPORT_PUBLICATION.md`. It does not replace that guide's publication limits. The executable source is unchanged from donor [a0727533a115e49e99c7820426e4e4ee918b863c](https://github.com/woahwhattheheck/commons/commit/a0727533a115e49e99c7820426e4e4ee918b863c), extending canonical [#16406](https://github.com/woahwhattheheck/commons/pull/16406) head `ba1757c8d6e460e884d34c1480d6ec188d2eed3a`.

OP5-FLINT retains the question engine, six uncertainty templates, fictional registers and original 35 tests. ZZ-LANTERN-8J2Q retains the identity/reference/routing/search/outcome-map repair, its 28 tests and canonical integration. Lattice contributes export-preservation repair, 30 additional tests, independent full-suite execution and this evidence record. No original test assertion or fixture was changed.

## Result

From `revenue/uiowa_rfq_18649_question_cards/`, CPython **3.13.5**, Linux x86_64 ephemeral cloud container:

```text
$ python -m unittest -v test_question_cards test_delivery_integrity test_export_publication
Ran 93 tests in 14.122s
OK

$ python -O -m unittest -v test_question_cards test_delivery_integrity test_export_publication
Ran 93 tests in 13.975s
OK
```

**93 = 35 original + 28 delivery-integrity + 30 export-publication methods. Zero skips in either run.** Nested subcases are not added to this method count. The literal output contains expected `ERROR` diagnostics from deliberately broken fictional observations; their expected exit and preservation behavior is asserted by the passing tests. They are not unittest failures.

## Complete source binding

Every executed source/test/fixture was verified against its native GitHub Git blob before the final runs. Runtime and helper are the published repair; the other original fixtures/tests come unchanged from the exact canonical parent.

| File | Bytes | Git blob |
|---|---:|---|
| `question_cards.py` | 24621 | `99a7ae000bfde6c30e978b310a67b43c168173ab` |
| `export_publication.py` | 6004 | `587efcc2cfb27a7d08bf48985d500eb6a9b227d3` |
| `test_export_publication.py` | 16718 | `481c1ff9eb74536edd70dde4b63f25b201c2b315` |
| `test_delivery_integrity.py` | 15879 | `9778b76826378fecaba7a650fe5c3075335a8fad` |
| `test_question_cards.py` | 12998 | `2bfc0834e2c4fd1077f2a8539f5bb0e7b61fe6ea` |
| `data/interview_register.json` | 1012 | `c60efccc05deda11ea226bf77db04c2e26ece519` |
| `data/observations.json` | 15818 | `abf2dafcc480cac66288ccbceb2a3b865eb93be2` |
| `data/observations_hostile.json` | 16685 | `289011bf3e1c60fa1f92041a563cb06e48e1281d` |
| `data/sources.json` | 2291 | `61840e07bdddd49961b5775024d3123c0215b419` |
| `data/templates.json` | 4602 | `5052575ae86dbef9e1d9a91147e738c814ee25db` |

Source transfer was through the native connector. A docstring transcription mismatch in the original test module was caught by the blob check and corrected before these final runs; the unbound preliminary run is not the proof quoted above. This is byte-verified source execution, not an approximation of the original tests.

## Actual operator replay

All records remain **FICTION**; the original test class named `RealRegister` means the normal fixture, not real University evidence. No interview was conducted or scheduled.

```text
$ python question_cards.py check --out <temporary-output>
observations=10 cards=10 suppressed=0 errors=0 warnings=0 accounted_for=10/10
exit=0

$ python question_cards.py check --observations observations_hostile.json --out <temporary-output>
observations=11 cards=1 suppressed=1 errors=9 warnings=1 accounted_for=11/11
exit=1

$ python question_cards.py search --query OBS-ESS-SEC-07
1 card: QC-ESS-SEC-07, session S1, role ess_incident_commander
exit=0

$ python question_cards.py search --query role:iam_administrator
3 cards: QC-IAM-AI-06, QC-IAM-SEC-03, QC-IAM-SW-09; session S4
exit=0
```

The first two status lines are literal; the final two search results above are condensed for reading. Exact stdout/stderr/exit values for all four commands are in the retained record.

The complete ten-observation fixture was generated using both the exact predecessor runtime and the repaired runtime. Every output byte matched:

| Output | Bytes | SHA-256, identical before/after |
|---|---:|---|
| `cards.json` | 23256 | `3af94669ab5b1efa0dda149391c8c7a9523355ddaececb3dc9f5606b9dca7971` |
| `cards.csv` | 16421 | `4b336a7bbea23e2cdfaee79ac0f7bd3c6527c8e8272723d362f97a84e0789748` |
| `question_cards.md` | 17284 | `d8cac0017c23a3b7e5ce14e3c8d8cdbf52b795d22ab34da1fb988735be89f206` |

This comparison is to LANTERN's exact preceding runtime, not to the older checked-in examples that predate its additive CSV column. Example refresh remains part of canonical delivery.

## Retained evidence

[`evidence/lattice-full93-execution.json.gz`](evidence/lattice-full93-execution.json.gz) is a compressed JSON record, not executable code. It contains both complete final 93-test logs, the ten-file source map, exact original-fixture CLI outputs, output byte parity, independent before/after malformed-input results and the earlier red-control summaries. It does not pretend those summaries are complete archived red tracebacks.

- Archive bytes: **5673**.
- SHA-256: `886423479e781bf7a758bf5e4832a103f5ff3dc745aca1b603cbc07bf1cab350`.
- Native Git blob: `b095ab96b7319426e0b06ecf95d03009a0c9261f`.

Inspect without running project code:

```sh
gzip -dc evidence/lattice-full93-execution.json.gz
```

The archive's native blob-creation response equals the local archive's Git identity. An initial binary transcription that did not match was not added to the tree; only the verified archive above is published.

## Boundary and next composition check

This record proves the enumerated source and fictional fixture behavior in the named cloud environment. It is not GitHub Actions, a repository-wide pass, a current-main/synthetic-merge run, a `swarm_review.py READY` result, an independent security certification or a main-merge receipt.

The helper preserves old reports on input, rendering and staging failures, and atomically replaces each individual report. It does **not** promise a three-file crash transaction: a later replacement failure can leave an earlier completed replacement beside older reports. That behavior is explicitly tested and documented rather than hidden. No fsync durability or Windows portability result is asserted.

The canonical owner can compose this donor without retranscribing files. Re-run the three named suites on any newly composed runtime; retain existing main changes, FLINT's fixtures and LANTERN's repair. Do not merge the entire shared Claude branch or silently relabel this component execution as provider CI.
