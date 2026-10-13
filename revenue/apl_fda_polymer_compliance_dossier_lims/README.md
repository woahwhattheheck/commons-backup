# APL FDA polymer compliance dossier LIMS

Demand: `apl-fda-polymer-compliance-dossier-lims-01`

This pack points to the root synthetic engine and acceptance binary:

```sh
python apl_fda_polymer_compliance_dossier_lims.py
python test_apl_fda_polymer_compliance_dossier_lims.py
```

The frozen 100-submission fixture reconciles regulated sample, lot, matrix,
intended use, method/version/instrument, QC, raw result provenance, and staged
FDA-supporting polymer evidence dossiers. The oracle is exactly 80 `READY` and
20 HOLD: 8 missing intended-use/regulatory matrix, 4 duplicate IDs, 4
method/matrix mismatches, and 4 QC/OOS failures.

Held rows create no accession, work order, result, staged dossier, or release.
Replay adds no records. Release uses an authoritative synthetic reviewer
directory and rejects automation or self-asserted reviewers.

HOLD / BUILD-AND-VERIFY. Synthetic/read-only. PRE-SALE TRANSPORT: NONE.
No customer data, live integration, outreach, spend, production write,
analytical interpretation, regulatory approval decision, or automatic release.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

