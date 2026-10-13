# Fixed-scope acceptance sheet — SaaS Migration Parity Pilot

## Paid diagnostic

**Price:** $5,000 fixed.  
**Input ceiling:** one sanitized source export and one sanitized target export, **≤500 records each**, with an explicit record-key mapping and up to 32 compared fields.  
**Delivery:** deterministic JSON evidence packet, concise buyer report, classification totals, row-level opaque commitments for holds/differences, and exact SHA-256 receipt/verifier instructions.

## Customer provides

1. Sanitized export files containing only fields necessary for the agreed parity check.
2. A stable source→target record-key mapping.
3. The exact source→target compared-field map and declared types.
4. Snapshot capture times and a truthful completeness declaration for the bounded exports.
5. The agreed cutover/freshness policy.

No production credentials are required for this fixed diagnostic.

## Acceptance criteria

The diagnostic is accepted when:

- both supplied files parse under the closed schema and size limits;
- the report deterministically classifies every union key as `PARITY`, `MISSING_TARGET`, `UNEXPECTED_TARGET`, `FIELD_MISMATCH`, `STALE_EVIDENCE`, `DUPLICATE_KEY`, or `INVALID_EVIDENCE`;
- report JSON verifies by exact deterministic recompilation from the same input bytes;
- raw record identifiers and values are not copied into the buyer report;
- exact input/report SHA-256 receipts are delivered;
- any stale, incomplete, duplicate, missing, unexpected, mismatched or invalid evidence remains visible instead of being silently converted to parity.

`PARITY_CONFIRMED` applies only when every union key is parity and both declared snapshots are complete and fresh under the supplied policy.

## Explicit exclusions

The $5,000 diagnostic excludes live provider API access, custom adapter development, production writes/cutover, remediation, data cleansing, identity resolution beyond the supplied key map, legal/compliance certification, and ongoing monitoring.

## Optional next scope

If the paid diagnostic establishes value and the customer wants live integration, a **$10,000 optional integration sprint** may be separately scoped against the actual source/target APIs, authentication model, rate limits, retry/idempotency requirements, cutover window and rollback needs. This is not bundled into the diagnostic and no free custom adapter is promised.

## Authority / commercial truth

This sheet is an offer scaffold, not evidence that any buyer accepted it. The software performs no customer contact, provider mutation, contract/signature, payment, cash or revenue-recognition action.
