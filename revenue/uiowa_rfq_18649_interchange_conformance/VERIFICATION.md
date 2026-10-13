# Version-bound executed verification

Executed 2026-09-19 in the ephemeral cloud container by ZZ-COPPERFINCH-4B7E92 / GPT-6 Astra Pro.

Runtime: Python 3.13.5. Synthetic preparation only. This is not hosted CI, merge authority or a University finding.

## Exact sources

| Role | Git blob | Bytes | SHA-256 |
|---|---|---:|---|
| Legacy baseline (PR #16197) | `7c43550f8fcb99cb5697dca3e16cf89ded1a46fd` | 12093 | `d31dae6cf3633999edee30c5b9e8215f8423327cd26671ae23d94577272ebc45` |
| Canonical candidate (TESSELLA PR #16236) | `735928df43423507dbf8206fb12e3d28112ed613` | 9890 | `0d9684aead6ab8d87d5bddd9b358c709d46635b424ed3fe4f888d854bf09c69f` |
| conformance.py | `9bd656c24b8efd9e0b7e1dfb5d2a78ac1a165b3d` | 14306 | `a05ed0049b3c78bdb286eb3655a1ea0bde23daaff924250dd5cca9afe56e4fff` |
| test_conformance.py | `b40e36fd36a6071fa15985a2397b2442860c3ddd` | 7539 | `143930e0524f29bf23f0fd98d289c96676fb9b6841b391537927ee7bb7bc4892` |
| synthetic.json | `e3bfe9996639d92ebfde5d5d775863e88ef32c5b` | 878 | `9a06f687931e5007ba2915be1bf830c4a18736c58a562b3c9290105163c0b326` |

Native GitHub readback matched all three harness/test/fixture blobs above at commit `664682a39d54424da7e87877307e79e8a1cf6402`. Both codec files were also byte-bound to native GitHub source before execution. These identifiers bind file bytes, not the complete dependency tree.

## Full 34-check result

The same fixture and document cases ran against both codecs. PASS means the stated case passed, not general losslessness. Rejection checks compare equivalent semantic corruption in each format, not identical byte mutations.

| Check | Legacy | Canonical |
|---|---|---|
| rows/fixture | FAIL | PASS |
| csv/fixture | FAIL | PASS |
| rows/root-null | PASS | PASS |
| csv/root-null | PASS | PASS |
| rows/root-scalar | PASS | PASS |
| csv/root-scalar | PASS | PASS |
| rows/root-array | PASS | PASS |
| csv/root-array | PASS | PASS |
| rows/empty-containers | PASS | PASS |
| csv/empty-containers | PASS | PASS |
| rows/empty-key-sibling | FAIL | PASS |
| csv/empty-key-sibling | FAIL | PASS |
| rows/numeric-object | FAIL | PASS |
| csv/numeric-object | FAIL | PASS |
| rows/nested-numeric-object | FAIL | PASS |
| csv/nested-numeric-object | FAIL | PASS |
| rows/escaped-keys | PASS | PASS |
| csv/escaped-keys | PASS | PASS |
| rows/unicode-distinct | PASS | PASS |
| csv/unicode-distinct | PASS | PASS |
| rows/presence | PASS | PASS |
| csv/presence | PASS | PASS |
| rows/number-types | PASS | PASS |
| csv/number-types | PASS | PASS |
| rows/line-endings | PASS | PASS |
| csv/line-endings | FAIL | PASS |
| rows/large-note | PASS | PASS |
| csv/large-note | FAIL | PASS |
| rows/formula-text | PASS | PASS |
| csv/formula-text | PASS | PASS |
| reject/duplicate-member | FAIL | PASS |
| reject/type-disagreement | FAIL | PASS |
| reject/missing-node | FAIL | PASS |
| reject/extra-node | FAIL | PASS |

**Legacy: 20 PASS / 14 FAIL. Canonical: 34 PASS / 0 FAIL.**

Eight failures are node/CSV pairs for the synthetic envelope, empty-key sibling, numeric-key object and nested numeric-key object. Legacy CSV also changes embedded CR/CRLF text and rejects a 140,000-character note at the parser default of 131072 characters. Four further failures silently accept duplicated, contradictory, omitted or additional rows. No failure is converted to a pass by changing the fixture.

Candidate PASS is for representable Python JSON values and CSV. TORQUE-47 independently identified precision loss in arbitrary-decimal raw JSON ingestion; that is not exercised away by these 34 passes. This recovery entry point rejects source decimal tokens that would round, and the tests cover those rejections. The original merged baseline attribution is unknown at seat level; it is identified by PR/blob, not assigned to TORQUE-47.

## Executed tests and commands

The documented configured test command ran **24 tests, all PASS**, normally and again under `python -O`. Missing canonical configuration deliberately produces an error. These totals are not added to the embedded 34-check audit to manufacture a larger independent-test count.

CLI audit on exact baseline returned 1 with the 14 failures above; audit on exact candidate returned 0. Original-source recovery also ran through the actual legacy writer and canonical reader, not only through the verifier’s expected-row helper.

Reproduction from an authorized checkout holding the recorded commits:

```sh
git show adeeefe4910b3d1c8aa54628053c60efcdb5bbfe:revenue/uiowa_rfq_18649_interchange/transport.py > /tmp/uiowa-old-transport.py
git show 5f3f1ce67d8b745118a002ea65a6915349d0a1f3:revenue/uiowa_rfq_18649_interchange/transport.py > /tmp/uiowa-canonical-transport.py
python conformance.py audit --codec /tmp/uiowa-old-transport.py
python conformance.py audit --codec /tmp/uiowa-canonical-transport.py
UIOWA_CANONICAL_CODEC=/tmp/uiowa-canonical-transport.py python -m unittest -v test_conformance.py
UIOWA_CANONICAL_CODEC=/tmp/uiowa-canonical-transport.py python -O -m unittest -v test_conformance.py
```

The shell example writes scratch source files; choose unused scratch names. Before trusting a reproduction, compare its returned source blobs with the table, not merely the branch name.

## Actual migration receipt

The checked-in synthetic source was emitted by the exact old `write_csv`, then recovered using the new `recover` function and reread through the exact canonical `read_csv`. Independent semantic comparison passed. All 30 old leaves became 41 explicit nodes; unchanged semantic identity is separate from changed raw transport identity.

```json
{
  "schema": "uiowa.interchange.recovery.v1",
  "status": "SOURCE_CONFIRMED_FORMAT_MIGRATION",
  "authority": "NO_AUTHENTICITY_OR_ASSESSMENT_ASSERTION",
  "codec": {
    "name": "transport.py",
    "bytes": 9890,
    "sha256": "0d9684aead6ab8d87d5bddd9b358c709d46635b424ed3fe4f888d854bf09c69f",
    "git_blob": "735928df43423507dbf8206fb12e3d28112ed613"
  },
  "original_json_sha256": "9a06f687931e5007ba2915be1bf830c4a18736c58a562b3c9290105163c0b326",
  "legacy_csv_sha256": "26b243c67409e98a08320ea1e27de7b29d7feb0af7f2471eb9a293070be89457",
  "new_csv_sha256": "beb52bac869d02f8e68851df7e7d7875bd3bae07880323e4b06f42c03c2cd3e7",
  "semantic_sha256": "58db9ffb03b008c30d216e9670b69b6a928e897ad0da90a9cf27d92b372c75f8",
  "legacy_rows": 30,
  "new_rows": 41,
  "limitation": "Original JSON is required; matching rows cannot establish which original produced an ambiguous legacy file."
}
```

The raw legacy CSV and regenerated canonical CSV can be reproduced from the committed fixture and exact source identities; this receipt does not authenticate an external original. The tests preserve originals byte-for-byte, refuse an existing destination, and leave no output for validation failures. Disk/I/O failures after creation are not an atomicity guarantee.

## Remaining integration boundary

The three-file source checkpoint is published on `swarm-zz/uiowa-096-conformance-4b7e92` / PR #16269; operator documents complete this carrier. No assertion here says the executable PR or canonical dependency is merged, hosted checks are green, or the complete delivery chain is accepted. Read the current PR/provider state separately.
