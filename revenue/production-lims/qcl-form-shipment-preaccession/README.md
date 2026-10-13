# QCL form/shipment pre-accession LIMS

Demand: `qcl-form-shipment-preaccession-lims-01`

This package is a **synthetic, deidentified, read-only shadow** for PDF/Word/email/shipment normalization into PRODUCT, RAW_MATERIAL, or STABILITY pre-accession workflows. Existing buyer/vendor systems remain authoritative.

## Frozen acceptance

`fixtures/qcl_200_intakes.json` deterministically expands to 200 paired synthetic intakes:

- 160 `READY`
- 7 `QUOTE_MISSING_OR_CONFLICT`
- 7 `PO_MISSING_OR_CONFLICT`
- 7 `METHOD_MISSING_OR_CONFLICT`
- 7 `LOT_MISSING_OR_CONFLICT`
- 6 `SAMPLE_QUANTITY_MISSING_OR_CONFLICT`
- 6 `STORAGE_MISSING_OR_CONFLICT`

Held intakes create no accession, workflow, test job, or staged report. Every READY normalized field retains its synthetic source-document SHA-256 and source coordinates (page/bbox, Word paragraph/run, email message/line, or package-label field). A full replay adds zero new state. Reports remain `STAGED_HUMAN_REVIEW`; release requires a named human.

Fixture SHA-256: `4ce6ccec57c446266869325973234ac458663f7d1d3657dc24ac66b51ac46d00`  
Expanded 200-record SHA-256: `5e3d25009c59703718c07a7d702ecc1f3a276f5681ef31416c319a6b443fba78`  
Manifest content-envelope signature: `1f201b1db55f0cae1dc76f9588193e369b34aa766f95f664f5fbd602492d28e5`

## Run

```bash
python -m unittest -v test_qcl_preaccession.py
```

No production writes, outreach, prospect-facing demo, automatic release, or real-record processing are part of this build.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
