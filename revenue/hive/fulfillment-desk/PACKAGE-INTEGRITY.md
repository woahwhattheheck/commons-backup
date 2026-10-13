# Parcel runnable-package integrity

Original operation: `PARCEL-RUNNABLE-PACKAGE-INTEGRITY-ZNSP8X4-20260913`  
Recovery/finalization: `PARCEL-RUNNABLE-PACKAGE-INTEGRITY-RECOVERY-ZPMN5V9-20260914`  
Carrier: Commons #14026

Parcel's client ZIP is a handoff artifact for the white-label fulfillment offer. The package now treats its manifest as an executable consistency gate instead of only a receipt.

## Build-side custody

`bundle.py` reads deployment and runner inputs through one retained file descriptor. On platforms with `O_NOFOLLOW`, the final path component is not followed; every consumed input must be a bounded regular file. The descriptor is fingerprinted before and after the read with mode, device, inode, size, mtime and ctime. A generation that changes while being consumed is rejected. Deployment JSON additionally rejects duplicate object keys and non-finite JSON constants.

The output file is created exclusively and the descriptor stays open through ZIP completion, `fsync`, byte counting and SHA-256 computation. Before success is reported, the visible output pathname must still name that exact created inode and size. Failure cleanup unlinks only that inode; a pathname that has been replaced by another file is never deleted as cleanup.

These controls close source/output generation confusion. They do not make an untrusted parent directory safe against every operating-system or privileged attacker.

## Runtime integrity

`MANIFEST.json` retains the existing exact `{sha256, bytes}` metadata for every packaged member and adds two explicit inventories:

- `runtimeImmutable`: code, branding/runtime HTML, Parcel handoff configuration, synthetic example, launcher and operating instructions;
- `operatorEditable`: only `config.local.json`.

`run.py` validates the manifest structure, file classifications and every immutable file's exact size and SHA-256 before loading `workflow.py`. The verified `workflow.py` and dashboard bytes stay in memory: the workflow is compiled/executed from that exact verified byte string and the branded dashboard renders from the verified HTML string, so neither path is reopened between verification and use.

Changing `config.local.json` is expected: it is the operator's local mapping/receiver configuration and remains editable. Its manifest hash is build-time receipt evidence, not a runtime lock.

This is an **internal package-consistency** check. It is not a signature, code signing, or independently authenticated provenance root. A party that can replace the launcher and manifest together can replace the internal verifier as well. Independently pin the ZIP SHA-256 or source delivery when authenticity matters.

## Regression contract

Commons now bounds live GitHub Actions and keeps candidate/product-specific definitions out of the active workflow surface. This recovery therefore does not restore the stale standalone `.github/workflows/parcel-package-integrity.yml` path from the Sep-13 branch. Instead, the already-retained `.github/workflows/revenue-hardening.yml` selects both `revenue/hive/fulfillment-desk/**` and the consumed `revenue/hive/intake-crm-workflow/**` paths and runs Parcel's package-integrity battery directly.

The Parcel step performs syntax compilation, the existing Node model suite, the existing bundle integration suite plus hostile integrity/custody tests in normal Python mode, and the same bundle/integrity suites under optimized `python -O`. The hostile suite covers immutable-member tamper, verified-generation reuse without pathname reopen, editable config, manifest reclassification, duplicate/non-finite JSON, source symlinks, same-inode mutation with restored mtime, output-path replacement and retained-inode result hashing.

No customer deployment, customer contact, payment, checkout, sale, or installation is established by these checks.
