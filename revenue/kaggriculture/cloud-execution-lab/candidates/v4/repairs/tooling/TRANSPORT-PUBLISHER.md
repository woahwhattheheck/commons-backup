# Exact-donor transport and canonical preservation

This tooling supports the single `main:candidates/v4` workspace specified by `../../CANONICAL.json`. It does not change production behavior, select a gameplay carrier, approve a checker, or invoke the historical materializer.

## Why this exists

The connector accepts literal UTF-8/blob content, not another session's local file handle. Large verifier sources were stranded as base64/gzip Git transports. A hash-locked public-repository GitHub job decoded them as data, published raw Git blobs, then fetched and compared the server bytes. No downloaded Python was executed.

Executed initial transport: workflow commit `7769151feb1bc09e94aaa07ae21a361c62faf460`; run `34665898053`; job `103477594741`; success. Raw objects:

- stage0 `29486689476e2c880021b26ac90b2ab7a407ff32` (74,960 bytes)
- patch1 `9d65c3f477aa708b4aa8b011acea6c3231ecb54f` (23,375 bytes)
- patch2 `de12e7c6520063df2dbacddefa96d2c1214983b4` (49,178 bytes)

Full SHA-256s and preservation status are in `../TRANSPORT-PRESERVATION-20260912.json` once the bounded preservation job lands. That receipt does not attribute earlier publication of the stage2 `12a3` scaffold to this transport run.

## Offline regression suite

From this directory:

```sh
python -m unittest -v test_preserve_transport_donors
python -O -m unittest -v test_preserve_transport_donors
```

No token or network is used by these tests. Executed locally against byte-for-byte server-matched source: **12/12 PASS normal and 12/12 PASS optimized**, plus `py_compile` PASS. These are tooling tests, not gameplay, materialized-package, or economic results.

Exact executed Git blobs:

- publisher `ff077716bb36d2ac3f057201bc332ad5783cb810` (7,339 bytes)
- tests `a539e95e4f1627e39d4deb754e30b1672049a2fd` (8,940 bytes)

Coverage: atomic three-path addition; idempotence; concurrent peer preservation; eight-attempt retry bound; conflicting existing file; symlink file; non-directory ancestor; changed canonical contract; truncated tree; corrupt blob; matching existing subset; rejection of other refs and force updates.

## Explicitly invoked publisher

`preserve_transport_donors.py` requires an authorized repository `GH_TOKEN` when run as a program. It has no import-time network calls. Its target inventory is hard-coded to the stage2 checker scaffold, historical fast-clone fold recipe, and the accompanying preservation receipt. It never imports or executes their contents.

Before writing it validates Git blob identities, exact regular-file modes, the current canonical contract and absence or byte-equivalence of each destination. A different existing file is a conflict, not permission to overwrite. It constructs a child of fresh main and requests only `force=false`; concurrent advancement triggers a bounded re-read/recomposition. It verifies destination objects on main after success. It is not a general-purpose merge bot.

The `12a3` checker remains **scaffold, not final C1 authority**. The `a83de6` fast-clone recipe pins a historical `apply_v4.py` ABI and must not be executed against current production. Semantic ports and promotion need their own current-ABI tests.
