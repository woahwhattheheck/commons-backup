# SOCOTEC CMT Network Federation — synthetic acceptance package

This additive package implements the frozen `socotec-cmt-network-federation-lims-01` build-demand contract as a **synthetic, read-only federation harness**. It does not connect to, mutate, replace, or certify any real SOCOTEC LIMS, QMS, scheduling, instrument, accreditation, reporting, customer, or provider system.

## Contract

- 500 deterministic synthetic jobs across 25 lab namespaces.
- Exactly 400 `READY` and 100 `HOLD`.
- HOLD truth set: scope, method-version, equipment, personnel-qualification, capacity, and duplicate-ID defects.
- Every `READY` job routes once to its golden namespace, personnel, method, equipment, and qualification.
- Cross-site transfers are accepted only by the synthetic predecessor→destination rule and a deterministic transfer ticket; unauthorized transfers fail closed.
- Mock legacy payloads are hash-bound and reconciled without mutation.
- Full fixture replay is idempotent and adds zero accessions, holds, reports, or events.
- Same submission ID with changed content fails closed as `REPLAY_PAYLOAD_CONFLICT`.
- Reports remain `STAGED_HUMAN_REVIEW`; release returns an unsent copy, requires a named human, rejects reserved automation identities, and never mutates the staged record. Automatic release is disabled.

## Run

```bash
cd revenue/production-lims/socotec-cmt-network-federation
python -m unittest -v test_socotec_cmt_federation.py
python -m py_compile socotec_cmt_federation.py test_socotec_cmt_federation.py
python socotec_cmt_federation.py fixtures/socotec_500_jobs.json fixtures/manifest.json
```

The fixture and manifest carry immutable SHA-256 evidence. The manifest also pins the deterministic post-first-pass audit-state digest. No real accreditation, compliance, capacity, routing, custody, test, or report disposition is asserted.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
