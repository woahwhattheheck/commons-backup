# Wyoming INBRE Campus Award, Trainee & Compute Evidence Rail — synthetic delivery core

This package is an **internal, synthetic acceptance implementation** of the approved Wyoming INBRE product definition. It is not a buyer deployment, NIH reporting system, award-management authority, or compliance certification.

## What it proves

The core accepts a bounded batch of flat synthetic records and deterministically reconciles:

- campus/project/period allocations and explicit amendments;
- exact-cent transfers that must preserve the network-wide authorized total;
- synthetic trainee appointments with exact allocation scope and overlap/duplicate refusal;
- shared compute/instrument usage that must map to an approved allocation scope or enter a named quarantine;
- report-evidence **hash pointers only** that must map to the same scope or quarantine;
- exact replay/idempotency behavior: an identical event ID+payload is collapsed with zero duplicate effect, while changed content under the same event ID fails closed;
- canonical roots and a SHA-256 receipt whose bytes are invariant to input ordering.

The fixture generator emits exactly **500 input records** across `CAMPUS-01` through `CAMPUS-10`: 495 unique records plus five exact retry replays. It deliberately includes five unmapped resource-use records and five scope-mismatched evidence pointers; acceptance requires all ten to be quarantined with the exact expected reason rather than silently counted.

## Acceptance commands

From the repository root:

```bash
python -m unittest revenue.wyoming_inbre_evidence_rail.test_rail -v
python -O -m unittest revenue.wyoming_inbre_evidence_rail.test_rail -v
python -m revenue.wyoming_inbre_evidence_rail.acceptance --write-receipt /tmp/wyoming-inbre-receipt.json
python -m revenue.wyoming_inbre_evidence_rail.acceptance --verify-receipt /tmp/wyoming-inbre-receipt.json
```

The acceptance CLI exits nonzero on any contract failure. Assertions are not used as production validation gates, so `python -O` preserves the same fail-closed behavior.

## Boundary

No research payloads, names, email addresses, phone numbers, SSNs/MRNs, dates of birth, student/participant identifiers, or nested opaque payloads are accepted. Use synthetic IDs only. The package does **not** select or score projects/trainees, approve appointments, initiate or authorize fund transfers, operate instruments/compute resources, decide NIH compliance, submit RPPR material, access buyer systems, or perform external effects.

`report_evidence` stores only a declared evidence kind and a caller-supplied SHA-256 pointer; the underlying document/data is intentionally outside this package.
