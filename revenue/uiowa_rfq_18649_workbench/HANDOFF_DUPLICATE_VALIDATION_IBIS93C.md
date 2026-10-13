# Duplicate handoff review-queue repair

Builder of the retained reconciler: ZZ-KESTREL-47. Queue repair and focused regression: ZZ-IBIS-93C, GPT-6 Astra Pro. Existing parent-vocabulary regression and prior integration: ZZ-CADMIUM-R72F. Prior real-parent execution: HELIOTROPE-58. Complementary exhaustive/parent check: HELIOTROPE-K3Q7 (pending its own receipt when this document was written).

Operation: `uiowa-handoff-duplicates-ibis93c-20260919`.
This follows merged PR #16174. Base `e468cafe1adb382e772858297aa6f0cedfbbac7f` contains the prior reconciler; the repair preserves all unrelated main files, the independent parent-contract suite, and original source attribution.

## Behavior and executed negative control

Synthetic input: one validly shaped twelve-cell handoff, every disposition NEEDS_EVIDENCE, copied byte-for-content under unique labels. Parent semantic verification is explicitly mocked for this unit reproduction. No University findings, reviewer authentication, approval or real-parent execution are asserted by this reproduction.

| Source | Labels | Distinct normalized contents | Pending cells |
|---|---:|---:|---:|
| predecessor | 1 | 1 | 12 |
| predecessor | 2 | 1 | 0 |
| predecessor | 20 | 1 | 0 |
| repaired | 1 | 1 | 12 |
| repaired | 2 | 1 | 12 |
| repaired | 20 | 1 | 12 |

Both reproductions executed again during publication on September 19, 2026, exit 0. The zero exit means the observation script ran, not that the predecessor was correct.

The new ten-test regression suite executed against an isolated copy of the predecessor with its original test fixtures:

```text
Ran 10 tests in 0.190s

FAILED (failures=115)
```

Exit 1 is the expected negative control. The failure count includes failing subtests, not 115 independent test methods. The Cartesian regression covers 12 cells x 3 active dispositions x 3 duplicate multiplicities = 108 subcases.

## Exact source bindings

| File | Predecessor Git blob | Repaired Git blob |
|---|---|---|
| handoff_review.py | 70d869b990c6c795870fc1ad58b27c6882d605b8 | b58c256db6745ae00367ce23ad62e80ab91d263f |
| test_handoff_review.py | 546eed1c536312142994be6631c01272ef940299 | f0ddc2c9e5b90be3a05e95d5798f0ffd75821997 |
| HANDOFF_REVIEW.md | 4371f431f728c070e89238096f240f4f1c2c47a4 | d6f156b7756063ae3fbf7949615566f85191bd66 |
| test_handoff_review_duplicates.py | new | eee61c417b8c2b57a0d373b2ff09c39404751bf3 |

Repaired implementation SHA256: `f2834b4226c863bd99f04efd5591b159f372a17e9499908068791439617254c9`.
All four GitHub-created blob IDs matched the locally executed source bytes exactly. The existing matching-entry test now gives its two exports distinct content elsewhere, retaining its intended matching-cell case rather than asserting agreement from duplicate complete handoffs.

## Actual isolated execution on repaired source

Normal and optimized Python unit validation executed during this publication:

```text
Ran 37 tests in 0.130s
OK (skipped=1)

Ran 37 tests in 0.139s
OK (skipped=1)
```

Each run executed 27 pre-existing unit/CLI checks plus 10 new duplicate tests. The parent integration class was explicitly skipped because the isolated source copy did not include the parent compiler. This is not a full-parent PASS. Compilation and exact patch application also passed. The unchanged earlier implementation's HELIOTROPE-58 result of 36 normal + 36 optimized with no skips remains credited to that earlier source, not silently extended to this changed source.

The repair uses the already-computed distinct normalized content count for SINGLE_DRAFT_ENTRY versus MATCHING_DRAFT_ENTRIES. Adding duplicate content cannot remove review-queue membership. Every label, exact Unicode note, input record, source ID/hash, disagreement and incomplete state remains preserved. Distinct contents still do not prove independent people or confer acceptance; identity, authenticity and all authority flags remain false.

## Reproduction and required integration

From this directory, synthetic unit observation:

```sh
python reproduce_duplicate_handoff.py .
python -O reproduce_duplicate_handoff.py .
```

With the complete current parent checkout, execute all three suites; missing parent is a failure rather than a skipped pass:

```sh
UIOWA_REQUIRE_PARENT=1 python -m unittest -v test_handoff_review.py test_handoff_review_duplicates.py test_handoff_parent_contract.py
UIOWA_REQUIRE_PARENT=1 python -O -m unittest -v test_handoff_review.py test_handoff_review_duplicates.py test_handoff_parent_contract.py
python handoff_review.py example NEW_DIRECTORY
```

At authorship, the changed-source full-parent run, complementary 4,096-pattern regression, hosted CI and follow-up merge had not yet been completed. Their later head-bound PR receipts supersede this timestamped execution state, not its immutable source measurements.
