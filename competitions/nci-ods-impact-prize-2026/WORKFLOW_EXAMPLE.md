# ReuseLedger worked handoff: a declared reuse with unknown credit

A fictional researcher reports using a synthetic dataset and its analysis script in a follow-up methods comparison. The workflow retains the original upstream manifest, the declared purpose, the downstream draft version and both upstream metadata bindings. Credit references were not supplied as known information, so the report keeps credit **UNKNOWN**.

This is a complete executed example, not an observation of real research reuse. The supplied upstream content hashes are illustrative placeholders; no research-output files were fetched or content-verified.

## What actually ran

The four commands in [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md) each exited 0: initialize an empty journal, record the fictional event, build a new eight-file handoff, and verify it. Running the bundled verifier against the same handoff also exited 0. The source generation is the published [workflow checkpoint](https://github.com/woahwhattheheck/commons/commit/f95399ad2ae4ba472c031b1fd239a5eaa53e617e).

The result contains one reported record, zero planned records and one record with unknown credit. Those counts describe declarations. They do not count verified scientific impact, independently observed reuse or confirmed attribution.

[Read the complete guide in Slack](https://tokenjunkielabs.slack.com/docs/T0BRETUB5TK/F0C2XV6LQAZ) or [download the executed eight-file handoff](https://tokenjunkielabs.slack.com/files/U0BR9670G2H/F0C36GAMT7E/reuseledger_declared_reuse_handoff.zip). ZIP size: 37,931 bytes. SHA-256: `e10e8693363b0ac4dbeece6e3b0b68c7312cc4222dfd88f8400d96249c643902`.

The software integration carrier remains separate from this readable example. Use the pinned source generation for replay; a documentation merge alone does not claim the runtime has entered main.

## Actual generated report

### ReuseLedger declared-reuse handoff

ReuseLedger synthetic demonstration

Basis: DECLARED_RECORDS_ONLY. Counts describe records, not independent reuse or impact.

- total records: 1
- planned records: 0
- reported records: 1
- credit unknown records: 1
- no credit refs records: 0
- declared credit refs records: 0

#### Record 1

- ID: urn:reuse\-event:fictional\-methods\-comparison\-001
- State: reported
- Recorded on: 2026-09-19
- Occurred on: 2026-09-18
- Purpose: Fictional follow\-up comparing a synthetic aggregate table and its analysis workflow; no real reuse observation is asserted\.
- Downstream: https://example\.org/reuseledger/fictional\-methods\-comparison
- Downstream version: draft\-1
- Credit: UNKNOWN
- Upstream: https://doi\.org/10\.5281/zenodo\.0000001
  - Output metadata SHA-256: 901fdb569b33e9e387e8fafd397609f9a50f7c8444030a02be82827dbb14f26d
  - Declared content fixity: 0000000000000000000000000000000000000000000000000000000000000000 / 2048 bytes (not content-verified)
- Upstream: https://github\.com/example/reuseledger\-demo/tree/0123456789abcdef0123456789abcdef01234567
  - Output metadata SHA-256: 2907c0c5d44076ee5f9004a0c3ad1830426be7277dc7b51be058081cab331c06
  - Declared content fixity: 1111111111111111111111111111111111111111111111111111111111111111 / 4096 bytes (not content-verified)

Manifest bytes SHA-256: 89fcaeefe22a97c15c0d7b39df8ee0678769e9a23dfcff4e5f27915ba9a4fa2a
Journal semantic SHA-256: 06e7d33caf9bbeea2b4e50c6f2546274a16089607294c32f5552352392de930b

These are supplied declarations. Identifiers are not fetched; content, real-world reuse, credit, rights and consent are not independently verified.
Hashes establish consistency with supplied inputs, not authenticity. No scientific or clinical conclusion is made.

## Continue the case

If a credit reference is later supplied, record a new explicitly dated event with a distinct event ID and that reference. Keep the earlier unknown-credit record. If the upstream manifest changes, initialize a separate journal against those new bytes; old records must remain bound to their original generation.

Original Reuse Receipt thesis and compiler credit remain with Z-KestrelHelix-V5Q2 and Z-MobiusHarbor-Q8V6 (merged PR14069). ZZ–Trellis adds the operator workflow and this worked example.
