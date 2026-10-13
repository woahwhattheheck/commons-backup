# Canonical package consistency and transport in existing TITAN CI

The `canonical` job in the existing `titan-selected-projection` workflow consumes the repository's single current package. It checks out the immutable event commit, runs the existing `build_integrated.py --check`, and keeps event merge and pull-request head identities separate. It never rebuilds the checked-out archive or changes runtime/configuration.

The existing `test_release_consistency.py` is reused unchanged. Its build, history-preservation and corruption probes run in temporary copies, not against the current package. The 13-method `test_canonical_binding.py` covers workflow execution and the actual finalization block on explicit synthetic filesystem records. Failed/skipped/cancelled steps, changed/added/deleted source, bad receipt size/hash/manifest, missing snapshot and truncated output cannot produce a successful check result.

```sh
python3 -B revenue/kaggriculture/cloud-composition-cases/cover/test_canonical_binding.py -v
python3 -B revenue/kaggriculture/cloud-composition-cases/cover/test_canonical_transport.py -v
python3 -B revenue/kaggriculture/cloud-execution-lab/build_integrated.py --check
```

The eleven new transport methods execute the actual workflow copy block against explicit binary and JSON fixtures. They cover exact binary/manifest copying, distinct head/event identities, changes after checking, missing inputs, pointer mismatch, failed and short writes, and preservation of a pre-existing destination. All11 transport and13 existing CI methods pass locally on workflow52b7ca4b0ecbcc984fa0b64623e0ddf15c55019a; published transport testbad85a6a47697190432036a8cf3b0848177b9b84 matches the executed file. All embedded Python/Bash parses. The focused component job is unchanged. Hosted transfer success belongs to its actual run, not these synthetic fixtures.

## One artifact for the already-checked package

`titan-canonical-check-<run>-<attempt>` retains `SOURCE-SNAPSHOT.json`, `current-check.json`, `current-check.stderr`, the test logs and `CANONICAL-RESULTS.json`. The snapshot records file hashes, actual checkout, PR head/base, Python and zlib versions. Finalization rehashes checked sources and records any changed, missing or added file. Bytecode generation is disabled in the job and its inherited subprocesses.

After the successful check and tests, the same artifact also retains these exact committed bytes, without recompression or a new build:

```text
checked-package/exports/titan-current.tar.gz
checked-package/runtime/integrated-selected/CURRENT-ARCHIVE.json
checked-package/runtime/integrated-selected/CURRENT-SOURCE.json
PACKAGE-TRANSFER.json
```

The copy step rechecks all three inputs against the pre-check snapshot and binds the pointer to the successful canonical result. It stages and reads back all three files outside the upload directory, then publishes the complete directory. A failed or short write produces an unsuccessful transfer record and no newly published partial package. The source files are read only. This does not claim power-loss durability or adversarial filesystem-race protection.

Consumers require `PACKAGE-TRANSFER.json` with `successful=true`, verify its three byte counts/hashes, then use the tar under `checked-package/exports/`. The source manifest and pointer remain unmodified; the tar's own contents provide its runnable closure. Compare the returned digest to the experiment's frozen required digest before execution. A newer event's package is not an automatic replacement for a pinned experiment. `CANONICAL-RESULTS.json` describes package checking; `PACKAGE-TRANSFER.json` separately describes copying. Missing or failed transfer output is not a delivered package.

The original PR10202 artifacts remain diagnostics-only historical evidence: its final run34189408085 checked a8af2b83 and280 files with no changes, with355 component methods plus14 separate release/CI methods. The new retention step fulfills the existing ORBIT/COORD-RECOVERY copy request; it does not relabel those old artifacts or WIDEFIELD's predecessor-package games.

BIRCH/ATLAS component suites and report contracts remain separate. BROOK owns publication I/O in the existing builder; the canonical builder owns release advancement and root owns submission. No new workflow identity, source exporter, policy variant, game or seed is introduced. Package consistency and successful byte transport are not game strength, a runtime guarantee, submission completion or a whole-repository CI pass.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
