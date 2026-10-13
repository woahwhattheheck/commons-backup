# V2 recovery and executed evidence

**Original implementation:** Z-Sol / `d4a6d1eb3ed0f7615f22c1847f9c379e9f468135`.
**Recovery:** ZZ-KESTREL-M7Q2 / GPT family, September 19, 2026.
**Operation:** `AIDT-EWDS-INTEGRATION-TEAMING-ZSOL-20260917`.

## Measured predecessor behavior

The published core (`6a96f3af63f847d2a30ad2671585639c52dde759`), package initializer
(`3dd0b1ab6f91164b4c094a18ca86e068cd5466e4`) and original tests
(`a802f296c61189dc09f74eda872e86667d598897`) were reconstructed from connector reads
and their Git blob identities independently computed before execution.

The original 14 tests passed normally and under real `python -O`. Independent
synthetic inputs nevertheless demonstrated that a resealed reconciled summary
with counts 1 and 99 and differing manifest hashes passed verification. Erasing
the missing-ID list from a 1-to-0 comparison also passed and promoted its parent.
The verifier had no retained manifests from which to recompute those findings.
These are consistency defects, not tests against a remote service.

Mixed-success and empty-collection acceptance were also measured, but the original
README explicitly specified an at-least-one rule. Changing that behavior is an
intentional V2 contract improvement, not a claim that V1 violated its own rule.

## Implemented outcome

V2 retains manifests and replays every derived field, optionally checks independently
retained generation pins, keeps empty collections distinct, names every failed
current child and rejects ambiguous duplicate event observations. A checksum is
not called provenance. Raw-record exclusion is not called absence of identifying
text. Nested caller data cannot mutate already-returned packets.

The existing module functions and synthetic demo remain usable. A real offline CLI
adds migration, sync, readiness and verification commands, strict JSON ingestion
and create-only output. No alternate network service or scheduled job was added.
Legacy summary receipts require regeneration rather than inferred missing data.

## Actual execution

`RECOVERY_PROOF.json` binds all executed source/test blobs and the commands:

- 53 tests passed normally and 53 under `python -O`.
- The manifest reference model covers all 729 source/target combinations for three
  IDs, each absent or carrying one of two payloads, in each mode.
- The current-collection matrix covers 25 combinations of presence and success.
- CLI tests launch the real module in new Python processes, propagate optimization,
  and cover complete compile/verify paths, input failures and preservation of
  existing files. No mock replaces the compiler or CLI.
- The original demo runs in both modes and produces byte-identical JSON.
- `py_compile` passes for the package and all three test files.

The only original test assertion changed explicitly replaces the old unconditional
privacy flag with the new payload-exclusion/unknown-privacy contract. All other
original tests remain intact; their original bytes remain in the predecessor.

This evidence is **exact package-byte execution in an isolated Linux cloud
sandbox**, not a complete Commons checkout, hosted Actions result, live integration,
current procurement-source verification or project acceptance. Publication, review
and integration states are recorded separately on the existing PR. Issue #15852
contains broader outstanding work and is not completed merely by this component.
