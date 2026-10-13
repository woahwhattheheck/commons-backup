# CSU malt cutoff and method-expansion bridge

Task: `csu-malt-method-expansion-lims-01`

Deterministic synthetic/read-only bridge for malt receipt, weekly cutoff routing, package-to-method expansion, internal/third-party routing, proficiency/QC gating, and staged reports.

## Frozen acceptance

- 80 synthetic submissions: 60 complete before cutoff, 8 complete after cutoff, 12 exact defects.
- Valid accessions route exactly 60 `CURRENT_WEEK` + 8 `NEXT_WEEK`.
- Holds: 4 `DUPLICATE_ID`, 4 `UNSUPPORTED_GRAIN_METHOD`, 4 `MISSING_IDENTITY_PACKAGE`.
- Exactly six designated `ASBC-PROTEIN` jobs route `THIRD_PARTY`; all other jobs route internally.
- Package expansion is defined by the frozen fixture manifest.
- One seeded QC-breach batch routes work but stages no reports.
- Replay is side-effect free; no duplicate jobs are created.
- Reports remain `STAGED_HUMAN_REVIEW`; release requires a named human.

No production/vendor/customer writes, compliance decisions, outreach, prospect-facing demos, or automatic report release.

```bash
python3 csu_malt_expansion.py
python3 test_csu_malt_expansion.py -v
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
