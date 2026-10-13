# AGT D7371 FAME FTIR — synthetic acceptance lane

This additive package implements `agt-d7371-fame-ftir-lims-01` as a **synthetic/deidentified, read-only intake → method/QC → staged-release acceptance harness**. It does not connect to, mutate, or certify any real laboratory, LIMS, FTIR instrument, customer, provider, fuel batch, specification, or compliance system.

## Frozen acceptance

- 100 deterministic synthetic chain-of-custody + FTIR records.
- Exactly 80 `READY`; 20 `HOLD`: 10 incomplete custody, 5 duplicate sample IDs, 5 synthetic-envelope OOS FAME results.
- Every READY record is bound to the synthetic contract's sample ID, method code/version, `% v/v` units, one-decimal reporting rule, QC/check-standard metadata, deterministic FTIR payload, and both FTIR/source SHA-256.
- All 20 exception records create zero accessions and zero staged reports.
- Exact replay is 100% idempotent and zero-add; same-submission changed content fails closed without state mutation.
- Accessions are unique by sample ID.
- Reports remain `STAGED_HUMAN_REVIEW`; release is copy-only/unsent, requires a named human, rejects automation identities, and automatic release is disabled.
- The `5.0 % v/v` gate in this package is a **synthetic test envelope only**, not an ASTM limit, product specification, or petroleum disposition.

## Run

```bash
cd revenue/production-lims/agt-d7371-fame-ftir
python -m unittest -v test_agt_d7371_fame_ftir.py
python -m py_compile agt_d7371_fame_ftir.py test_agt_d7371_fame_ftir.py
python agt_d7371_fame_ftir.py fixtures/agt_100_records.json fixtures/manifest.json
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
