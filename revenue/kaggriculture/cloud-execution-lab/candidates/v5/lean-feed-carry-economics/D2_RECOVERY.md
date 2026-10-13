# D2 source recovery gate

Operation: `TITAN-V5-LEAN-FEED-D2-EMPIRICAL-20260917`

Issue #14337's remaining empirical gate needs the exact frozen TITAN V5 D2
package, not a reconstructed approximation. The exact binary is not present in
the checked accessible GitHub/Slack/Library/Drive surfaces, so this lane does
**not** claim an empirical economics result.

This directory now contains `d2_archive_authority.py`, a fail-closed ingress
verifier for the next appearance of those bytes. It never extracts or executes
archive members.

## Frozen custody target

- archive: `titan-v5-runtime-one-timer-variant-d2-prewarmed.tar.gz`
- SHA-256: `3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8`
- exact bytes: `424145`
- exact tar members: `94`
- payload `main.py` SHA-256: `ae7032281ba680cc70fdfc333bb55cbd4aab7127c277c5150f18746c12f549d3`
- retained runtime member: `titan_runtime.py`
- retained runtime Git blob: `e0cdcf5a5dbe350d442d3b492795d37507449853`
- retained `operating_stock.py` Git blob: `80b372bfd34d04a2c9e2376fa02917f21f659c41`
- official interpreter SHA-256: `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`
- harness SHA-256: `853850d8673cff0b21fdfe783e2dfcd539b8b2707bfe2d36c2e60d8ec2e43ea4`

The prior runtime/release receipts also pin the archive at 424,145 bytes / 94
members and the same `main.py`, engine, and harness hashes. Hash receipts are
custody evidence; they are not substitutes for the missing archive bytes.

## Verifier contract

`d2_archive_authority.py` authenticates the raw gzip-tar byte size and SHA-256
before trusting tar contents. It then reads members in memory without
extraction and fails closed on:

- absolute, traversal, backslash, or normalization-drifting paths;
- duplicate normalized member names;
- symlinks, hard links, devices, FIFOs, sparse/special entries;
- member-count drift;
- non-unique or hash-drifting `main.py`;
- retained runtime-path / Git-blob drift; or
- missing retained `operating_stock.py` Git-blob identity.

For every regular member, the receipt records its byte size, SHA-256, and Git
blob ID. The safe-member manifest is itself SHA-256 bound. Optional engine and
harness sidecars must match their frozen SHA-256 values before
`execution_inputs_ready=true`.

Even a successful archive check returns:

```text
source_authority_verified=true
candidate_build_authorized=false
promotion_authorized=false
```

Source authentication is necessary, not sufficient. It does not bypass the
WHEAT-only census, prospective development panel, untouched holdout, independent
review, or code-retained trusted-root requirements already landed for #14337.

## Commands

Current environment with no archive bytes:

```bash
python d2_archive_authority.py
```

Recovered archive, source authentication only:

```bash
python d2_archive_authority.py \
  /path/to/titan-v5-runtime-one-timer-variant-d2-prewarmed.tar.gz \
  --engine /path/to/pinned_interpreter.py \
  --harness /path/to/pinned_harness.py \
  --out /tmp/d2-authority.json
```

Validation of the verifier itself:

```bash
python -m py_compile d2_archive_authority.py test_d2_archive_authority.py
python -m unittest -v test_d2_archive_authority.py
python -O -m unittest -v test_d2_archive_authority.py
```

Authored-equivalent validation on 2026-09-17: 17/17 normal PASS, 17/17
optimized PASS, compilation PASS.

## Current recovery census

The exact archive (`titan-v5-runtime-one-timer-variant-d2-prewarmed.tar.gz`,
SHA-256 `3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8`)
was located on operator workstation storage alongside pinned execution engine
`bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e` and
harness `853850d8673cff0b21fdfe783e2dfcd539b8b2707bfe2d36c2e60d8ec2e43ea4`.
Running `d2_archive_authority.py` against this archive authenticates all 94
members, yields safe member manifest SHA-256
`d0c150d5be46a6f5e5b3275197c0f3279f4f7345b61e0ff917196db5a1eca84c`, and produces
authenticated receipt SHA-256
`df11fce3b91bcf36ad280942ed38e1faed743ce3b23fbb6f8b8e8a5ada65fb46`.
The machine-readable state is `D2_RECOVERY_STATUS.json`.

No CURRENT/default/archive pointer, Kaggle submission, provider/account,
payment, prize, gameplay, or competition state is changed by this recovery
carrier.
