# Real/REMAX transaction cutover evidence core

This package is an **offline evidence gate** for a source→target brokerage transaction migration. It does not connect to a brokerage, MLS, TMS, escrow, payment, licensing, or production system. Synthetic or buyer-authorized offline exports are the only intended input.

## What it proves

For every source transaction whose source stage is in the policy's active set, the compiler requires a one-to-one mapped target transaction and checks:

- source/target office and agent identity maps are one-to-one, contain no orphan rows, and resolve to retained snapshot rows;
- each mapped target agent remains in the mapped target office;
- source stage and status map exactly through a closed policy map;
- gross commission matches in integer cents;
- relationship role, mapped agent, split basis points, and relationship commission cents match exactly;
- relationship commission cents sum exactly to gross and split basis points sum to 10,000 in each snapshot;
- required roles remain present;
- active source transactions cannot disappear or point to a missing target row.

Every supplied transaction-map row must resolve both endpoints to the retained source and target snapshots. The map may also contain valid mappings for inactive source transactions; those rows remain bound evidence, while `PARITY` evaluates only source transactions whose stages are in `active_source_stages`.

The report binds the normalized semantics of the source generation, target generation, identity map, and policy by SHA-256. Array order is normalized before hashing, so reordering offices, agents, transactions, relationship rows, or identity-map rows does not change the report or receipt; IDs, generation numbers, mappings, values, stages, statuses, cents, and splits still do. `verify_report()` recompiles semantics and requires canonical report equality, so resealing a modified report is not sufficient.

## Truth boundary

A `PARITY` result means only that the supplied, internally valid offline generations satisfy this package's deterministic cutover contract. It is **not** evidence of legal/licensing compliance, brokerage approval, commission entitlement, production cutover, agent/customer notice, buyer acceptance, payment, escrow/disbursement, or recognized revenue. All such authority fields are hard-false in the report.

## Synthetic acceptance fixture

`synthetic_fixture.build_synthetic_bundle()` builds 240 active transactions across four offices and 32 synthetic agents. The root test bridge exercises all 240 as a clean acceptance corpus and then attacks stage/status drift, exact-cent drift, split/relationship drift, office mismatch, missing/ambiguous/orphan mappings, duplicate identities, receipt tamper/reseal, source-generation drift, full-report order invariance, findings-ceiling failure, aggregate direct-object bounds, strict duplicate/non-finite/deep JSON, create-exclusive publication, post-durability foreign-successor pathname swap, and CLI write/fsync/parent-create publication failures under normal and optimized Python.

## Resource and publication custody

CLI inputs must be strict canonical UTF-8 JSON. Duplicate keys, non-finite values, non-regular input files, oversized inputs, excessive JSON depth/node count, input-generation mutation during read, and non-exclusive output paths fail closed. The direct Python object API separately enforces aggregate snapshot and identity-map row ceilings before expensive derived-map construction, in addition to per-list/per-relationship limits.

Output creation is exclusive. On platforms with `dir_fd` support, the writer retains the output parent descriptor as well as the output file descriptor through write/fsync and the final publication check. Before success, it requires the visible leaf to remain a regular file with the same device/inode generation as the retained output descriptor and requires the visible parent pathname to still resolve to the retained parent generation. On platforms without `dir_fd`, it performs the same non-followed final leaf-generation check by pathname. Failed output publication truncates only the retained owned descriptor best-effort and never pathname-unlinks a possible foreign successor; an owned zero-byte tombstone may remain for explicit cleanup. Filesystem failures during parent preparation, output write, or output-file fsync are normalized into the same `CutoverError` CLI contract after descriptor-only rollback, so they emit `ERROR:` and exit 4 rather than escaping as tracebacks.

## CLI

```bash
python -m revenue.real_remax_transaction_cutover.cli compile \
  --source source.json \
  --target target.json \
  --identity-map identity-map.json \
  --policy policy.json \
  --output report.json

python -m revenue.real_remax_transaction_cutover.cli verify \
  --source source.json \
  --target target.json \
  --identity-map identity-map.json \
  --policy policy.json \
  --report report.json
```

Exit codes: compile `0=PARITY`, `2=HOLD`, `4=input/contract/publication error`; verify `0=VERIFIED`, `3=INVALID`, `4=input/contract error`.

## Lineage

Recovery implementation for Commons issue #13800. Original commercial trigger/scope/source credit remains Z-Cyclotomic-913645-R5K8 (`ZCYC-R5K8`). Recovery/source/test/finalization lane: Swarm Z / GPT-5.6 Sol, operation `REAL-REMAX-TRANSACTION-CUTOVER-EVIDENCE-RECOVERY-ZSOL-20260917`.
