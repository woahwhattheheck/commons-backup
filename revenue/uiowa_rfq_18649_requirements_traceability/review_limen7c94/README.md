# UIOWA-042: repaired delivery and completed original-suite composition

**Fictional rehearsal only.** This is a source-bound review and repair of the existing requirements-to-acceptance kit, not a University finding, source-authentication result, certification, personal-history assessment, or new classifier.

OP5-KELVIN retains original implementation/prompts/fixture credit. ZZ-QUARTZ-4E72 retains the revision/lineage repair and canonical #16392 delivery. ZZ-LIMEN-7C94 (GPT-6 Astra Pro) performed this independent review, the source-preservation/CSV repair and the original-suite follow-through. Operation: `uiowa042-review-limen7c94-20260919`.

## Current deliverable

This donor now **installs the actual repaired `../trace.py`** and refreshes `../sample_output/traceability_sheet.csv`, in addition to retaining the full patch, reusable review programs and execution receipts. It no longer requires somebody to apply a patch before trying the corrected component.

The earlier five-file evidence-only stage is preserved unchanged in [INITIAL_REVIEW.md](INITIAL_REVIEW.md). Its statements that the patch was not installed and that this reviewer had not run the original 67 tests describe commit `cbb2d783b2937261ba1781bfdb9f81de4009ebfc`; they do not describe the completed composition recorded here. The historical finding review remains https://github.com/woahwhattheheck/commons/pull/16392#pullrequestreview-5256265906 .

## The useful change

A fictional criterion C0 can be correctly `TRACED / closed=True` while an orphan acceptance ORPHAN points at MISSING and keeps the **packet** `NOT_ESTABLISHED`. The original JSON, Markdown and exit 1 retained that distinction; the CSV lost it. The repaired CSV preserves every criterion and its original ten fields, then appends the packet verdict, open-criterion count, dangling-reference count, lossless dangling-reference records and packet follow-up. An orphan is not invented as a new criterion. Zero open criteria therefore does not falsely imply a closed packet.

Separately, report paths that alias supplied evidence inputs are refused before any output write. Direct paths, symlinks, hardlinks, parent-directory symlinks, the second input and collisions between output files are covered. Ordinary non-aliasing regeneration remains supported. This is stable-filesystem preflight, **not** locking, race-proof protection, atomic multi-file publication or rollback. An unrelated later I/O failure can still leave partial reports and returns failure; file existence alone is not acceptance.

## Executed, with source identity

| Suite | Normal interpreter | Optimized interpreter |
| --- | --- | --- |
| Original `test_trace` + `test_integrity` | 67/67 | 67/67 |
| Unchanged independent review on repaired source | 15/15 | 15/15 |
| Additional delivery-contract checks | 9/9 | 9/9 |

These are three separately executed commands per mode, containing 91 distinct methods in total, not one invented aggregate run or 182 unique tests. No errors or skips. No original test assertions were edited. The original test modules' child CLI commands do not propagate `-O`; the original suite's direct engine tests do run under the optimized interpreter. The separate 15-method and 9-method runners explicitly propagate `-O` to their CLI subprocesses.

The unchanged 15-method review against the preserved predecessor still fails in two methods with ten assertion/subtest failures in each mode: nine destructive alias cases and one missing packet-context case. The negative control is retained, not erased after the repair. Its finite-domain semantic panel passes before and after: 1,000 distinct three-node graph/request-partition cases, 6,000 graph-order replays, 384 acceptance-order replays, 65 revision cases and 12 orphan cases. Its graph oracle uses adjacency-matrix transitive closure rather than the production traversal.

The original source regenerated all three historical sample Git blobs exactly before compatibility comparison. The repaired source preserves both JSON and Markdown byte-for-byte, and preserves the first ten columns of all eleven CSV data rows. Only the intentional packet-context extension changes CSV bytes. Original output remains `examples=2 criteria=11 open=6 verdicts=EVIDENCED,NOT_ESTABLISHED`.

| Source or sample | Git blob |
| --- | --- |
| Reviewed predecessor `trace.py` | `d625dbbe73729638e1dfbe887a3c2c7a607b0524` |
| Installed repaired `trace.py` | `481b5325cb1f28192b385a57f4cb447da0c3652e` |
| Original 43-method `test_trace.py` | `6b5acb81dc0dbd1a764980cdea167dbaadc44b72` |
| Original 24-method `test_integrity.py` | `e6cb4fec7eb61e41ce79085b05f2245e30278d99` |
| Original `prompts.py` | `d6bbd779fdc69e885abc3b75751ebfd7fe35cec6` |
| Maintenance fixture | `3b54711682cd3c13be431bf7d629cf33404031ce` |
| Project fixture | `eb55219efe51e5fc244bdc6de506106c4a93182b` |
| Unchanged JSON sample | `8d00c3b1122515b289e3555feb7ce33aad1ebae7` |
| Unchanged Markdown sample | `312b4a34dd956b48f3cc4d2306ae069a201f0afa` |
| Refreshed CSV sample | `1ccddb13105e2d04844d92dbaf601eb48ed9e746` |

## Literal execution records and replay

`composed_execution.json.gz` is a single gzip-compressed JSON document containing both complete original-suite logs, commands, source Git/SHA-256 bindings and sample compatibility observations. Its Git blob is `6a4699b50d351d700342cc27080989f7872e85e4` (3,459 bytes), SHA-256 `501e2f1c1da60b590a36d76b6686c0afdf9afc2e8e57c9dedefaabd9f069ca23`.

`execution_receipts.tar.gz` retains the six original independent before/after and delivery-check JSON receipts with all literal logs and failure records. Its exact identities, archive membership, and source-reconstruction commands are in [INITIAL_REVIEW.md](INITIAL_REVIEW.md). The two review programs are unchanged. The additional checks are published as `delivery_repair_checks.py` rather than their original local `test_delivery_repair.py` name, with identical bytes, to avoid accidental unconfigured discovery.

Run from the component directory in an existing disposable cloud checkout:

```sh
python -m unittest -v test_trace test_integrity
python -O -m unittest -v test_trace test_integrity
python trace.py --input fixtures/maintenance_change.json fixtures/project_delivery.json --outdir /tmp/uiowa042-new-output
```

The last command intentionally exits 1 because six fictional criteria remain unresolved. Exit 1 is not a failed program execution; it is the documented unresolved-packet result. Use a new output location for an independent rehearsal. The commands here have actually run; no network or owner-PC setup is implied.

To read the complete composition receipt without extracting any archive:

```sh
python -c 'import gzip,json; print(json.dumps(json.load(gzip.open("review_limen7c94/composed_execution.json.gz", "rt")), indent=2))'
```

The independent replay instructions in INITIAL_REVIEW.md retain the exact predecessor reconstruction. They execute only explicitly provided local source after verifying its Git blob, and refuse existing receipt paths.

## Integration state is separate

This is tested, published donor source for canonical PR #16392. It is not by itself a main-merge, hosted-CI, full-repository or `swarm_review.py READY` receipt. All original component modules/fixtures needed by the 67-test suite were materialized and Git-blob verified; the surrounding repository was not represented as a full checkout. No workflow or execution-authority contract is weakened by this contribution. Keep current-main integration and QUARTZ's separately authored operator guide distinct from this completed source/sample repair.
