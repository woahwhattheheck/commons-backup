# Bowser-Morner Cross-Lab Method & Custody Gate

Synthetic/read-only implementation for demand `bowser-morner-crosslab-method-lims-01`.
It complements incumbent systems; it does not write to a LIMS, instrument, QMS, custody,
or report system and it never performs automatic quality disposition.

## Fixed fixture contract

The committed 120-row fixture contains 100 intake-valid specimens spanning concrete,
aggregate, soil, asphalt, and specialty chemistry plus 20 deterministic intake defects:
7 out-of-scope/method-scope, 7 incomplete, and 6 duplicate specimen IDs. Valid rows are
routed to immutable Dayton/Toledo/Springfield lab+method+revision+preparation contracts.
A fixture-only calibration defect on `TOL-AGG-03` blocks every staged report in that run.
All other reports remain `REPORT_STAGED_HUMAN_REVIEW`; only the named human fixture
reviewer can produce a detached release record.

The route rules and test thresholds here are synthetic acceptance-fixture data, not claims
about Bowser-Morner's production methods, accreditation, or live quality rules.

## Reproduce

```bash
cd revenue/production-lims/bowser-morner-crosslab-method
python3 test_bowser_morner_gate.py
python3 bowser_morner_gate.py fixtures/bowser_120_specimens.json.gz.b64
```

`fixtures/manifest.json` pins both the deterministic gzip/base64 fixture SHA-256 and decoded JSON SHA-256 and expected deterministic manifest/audit
hashes. Re-running the same fixture produces byte-identical canonical output and zero new
accessions or state transitions because the harness is a pure read-only shadow projection.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
