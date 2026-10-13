# Mapping Equity sealed-generation successor

Operation: `MAPPING-EQUITY-M1-MEMFD-SEAL-FIX-ZRHH7N4-20260914`  
Owner/finalizer: Z-RhodiumCauseway-2026-H7N4 (`ZRH-H7N4`) / GPT-5.6 Sol  
Tracking issue: #14591  
Predecessor: #14579 / main merge `44febdab2c78e8e3ab092bf4e6a83f598507413d`

## Why this successor exists

The #14579 generation repair correctly stopped reopening the remote URI, but its anonymous `tempfile.TemporaryFile` inode was still owner-writable. Closing the original writer and retaining only a read-only descriptor does not make that inode immutable: `/proc/self/fd/<retained-fd>` is a proc magic pathname that can be freshly opened `O_WRONLY`, after which `pwrite()` can modify the exact inode consumed by DuckDB.

That recreates the authority split the fix was intended to remove: preflight can validate generation A, a local write-reopen can mutate the inode, and scored aggregation can consume generation B from the same retained descriptor path.

## Kernel-enforced closure

The live `aggregate.py` is now a narrow authority wrapper around the exact #14579 runner, preserved byte-for-byte as `_aggregate_unsealed.py`. Scoring SQL, filters, URI policy, schema checks, output validation, receipt construction, CLI behavior, and all other helpers remain the landed implementation. Only `_stream_response_to_retained_fd()` is replaced.

The replacement:

1. requires Linux `os.memfd_create(..., MFD_ALLOW_SEALING)` and fails closed when kernel/Python seal support is unavailable;
2. streams the one admitted HTTPS response into the memfd while computing the same SHA-256 and byte count;
3. fsyncs the completed bytes;
4. applies and verifies `F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL`;
5. only then exposes a read-only `/proc/self/fd/<n>` handle to the unchanged preflight/scoring pipeline;
6. closes the construction descriptor while the kernel seals persist for the inode lifetime.

The receipt-facing generation identity remains `sha256:<digest>` with the same URI/SHA-256/byte-count fields.

## Predecessor killer

`test_memfd_seal.py` explicitly reopens the retained proc path with `O_WRONLY`. On the old #14579 tempfile construction, `pwrite()` succeeds. On the sealed successor, both `pwrite()` and `ftruncate()` fail with `EPERM`, the required seal mask is present, and the retained bytes remain exactly unchanged.

Run with the existing contract/recovery suites:

```bash
python -m py_compile aggregate.py _aggregate_unsealed.py test_aggregate.py test_recovery.py test_memfd_seal.py
python -m unittest -v test_aggregate.py test_recovery.py test_memfd_seal.py
python -O -m unittest -v test_aggregate.py test_recovery.py test_memfd_seal.py
```

No Zindi registration, submission, leaderboard, prize, payment, or revenue claim is performed by this repair. Hosted real-data execution remains separate provider truth.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)
