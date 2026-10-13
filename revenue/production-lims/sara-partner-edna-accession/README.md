# SARA partner eDNA/qPCR accession shadow

Demand: `sara-partner-edna-accession-lims-01`

A deterministic, synthetic/read-only reconciliation package for San Antonio River Authority Regional Environmental Laboratory partner/client submissions. It models COC/container intake, facility/scope/panel routing, qPCR control-batch binding, QA holds, report staging, and replay idempotency without contacting or writing any production system.

## Frozen acceptance

`python -m unittest -v test_sara_partner_accession.py` and `python sara_partner_accession.py` must reproduce:

- 240 expanded synthetic submissions;
- exactly 192 `READY` and 48 `HOLD`;
- exactly 8 holds for each of `MISSING_SUBMITTER_OR_CUSTODY`, `MATRIX_ANALYTE_MISMATCH`, `DUPLICATE_ID`, `HOLD_TIME_BREACH`, `PARTNER_CLIENT_IDENTITY_MISMATCH`, and `QPCR_CONTROL_FAIL`;
- the two seeded failed qPCR control batches hold all eight represented batch members;
- every READY submission creates exactly one accession, one job, and one unsent `STAGED_HUMAN_QA` report with the expected facility, accredited-scope route, panel version, control batch, program/client identity, and source/custody/report digests;
- held submissions create zero jobs and zero reports;
- no report crosses program/client identity;
- full same-ledger replay adds zero state;
- release is copy-only, unsent, and requires a non-reserved two-token named human reviewer; automatic release is disabled.

The compact fixture is a signed deterministic generator. `manifest.json` pins both its file SHA-256 and the SHA-256 of all 240 expanded records, plus the exact truth-set distribution.

## Boundary

Synthetic/deidentified inputs only. This package makes no public-health, regulatory, accreditation, compliance, diagnostic, or release decision. It performs no production/state/provider/customer write, no external send, no outreach, no spend, and no autonomous release. A real integration requires buyer/vendor-approved schemas and golden round trips outside this repository fixture.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
