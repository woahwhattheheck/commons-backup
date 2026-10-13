# ats-asphalt-spec-result-lims-01 receipt

State: TESTED
Binary: `python3 test_ats_asphalt_spec_result_lims.py` → 10/10 OK
CLI: `python3 ats_asphalt_spec_result_lims.py` → ok true, failures []

| check | expected | actual |
|---|---|---|
| input jobs | 60 | 60 |
| worklist | 48 | 48 |
| intake HOLD | 12 | 12 |
| HOLD codes | two each of MISSING_SPEC, WRONG_UNIT, INSUFFICIENT_QUANTITY, DUPLICATE_ID, METHOD_REVISION, EXPIRED_CALIBRATION | two each |
| in-spec | 46 | 46 |
| Hamburg OOS review hold | 1 (ATS-PERF-01) | 1 |
| binder invalid review hold | 1 (ATS-BIND-01) | 1 |
| human releasable | 46 | 46 |
| human released | 46 | 46 |
| autonomous released | 0 | 0 |
| replay added records | 0 | 0 |
| audit_sha256 | 3c09bd0ca3c6f03194611a5d7aca63f2e80df7e596ef8f7137801a1cdd9bbae9 | 3c09bd0ca3c6f03194611a5d7aca63f2e80df7e596ef8f7137801a1cdd9bbae9 |

Buyer: Asphalt Testing Solutions & Engineering / Tanya Nash.
Interfaces simulated/read-only. No live QC decision, production write, billing, or automatic report release. AquaTrace HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

