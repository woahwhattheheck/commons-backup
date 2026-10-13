# corrigan-specialty-fuel-blend-dossier-lims-01 receipt

State: TESTED
Binary: `python3 test_corrigan_specialty_fuel_blend_dossier.py` → 9/9 OK
CLI: `python3 corrigan_specialty_fuel_blend_dossier.py` → ok true, failures []

| check | expected | actual |
|---|---|---|
| input orders | 80 | 80 |
| CLEAN | 64 | 64 |
| HOLD | 16 | 16 |
| FORMULA_VERSION_MISMATCH | 8 | 8 |
| MISSING_EXTERNAL_RESULT | 4 | 4 |
| OOS | 4 | 4 |
| batches | 72 | 72 |
| duplicate batches | 0 | 0 |
| orphan tank movements | 0 | 0 |
| staged CoA | 64 | 64 |
| genealogy | 64 | 64 |
| human disposed | 64 | 64 |
| autonomous released | 0 | 0 |
| production writes | 0 | 0 |
| replay added records | 0 | 0 |
| audit_sha256 | 85f8acfab58b66c1022fffcefeef49bef19cb7c3e36db65c4c912de74ab754fe | 85f8acfab58b66c1022fffcefeef49bef19cb7c3e36db65c4c912de74ab754fe |

Buyer: Corrigan Labs / Mike Corrigan.
Interfaces simulated/read-only. No live LIMS, production write, outreach, or automatic release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
