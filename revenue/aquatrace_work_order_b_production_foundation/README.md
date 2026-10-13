# aquatrace-work-order-b-production-foundation-20260831-01

Working program for AquaTrace **Lane B — Production foundation**: roster lookup, deny-by-default RBAC, attributable audit, samples/custody/QC, and device contracts.

The runner is the product. `python3 aquatrace_work_order_b_production_foundation.py` performs intake → roster lookup → deny-by-default RBAC → attributable audit → sample/custody/QC transitions → device-contract check → HOLD on violations → named-human release. Tests prove that program. The HTML window is not the product.

Synthetic actors and packets only. No live LIMS. No production writes. No automatic release. No City / customer data. No outreach. No bid. No readiness or certification claim. State remains **NOT_READY**. **HOLD / BUILD-AND-VERIFY**. `cash_usd=0`.

Cite Billings instrument fixtures conceptually (`mock-ph-meter-1`, `mock-metrohm-ic`, `mock-analytical-balance-1`). Those files are not rewritten. Do not edit the private `woahwhattheheck/aquatrace-lims` repo.

## Boundary

- Unknown and disabled actors refused.
- Each role stays in named scope. Same actor cannot approve a change they proposed.
- Support is time-bounded and cannot silently elevate.
- Integration cannot administer users. QA cannot erase audit.
- Reporting can release only reconciled, QC-approved packets.
- QC holds and unknown devices block release.
- No result without a named human. Replay produces at most one effect.
- Open Door on Commons is unchanged. RBAC here is the synthetic LIMS product, not a Commons login gate.

Cite, do not remint: work orders A / C / D, D-QA, `sanair-asbestos-coc-router-lims-01`, westpak PR 6815 blob `f282a9ed`, ddl PR 6820 blob `b8a191e3`, highpower PR 6819 blob `374b4cdf`, wadsworth PR 6817 blob `09ef29fa`, sharp PR 6818 blob `b139c7eb`, billings-bid-1421 runners and instrument-fixtures, pcl, canyon, weck, kincell, organabio, elevatebio, made-scientific, roslinct, savant-fe8, SKUs 1–7, PR 6813, fire_action, $5 tip.

## Official command

```bash
python3 aquatrace_work_order_b_production_foundation.py
python3 revenue/aquatrace_work_order_b_production_foundation/runner.py
python3 test_aquatrace_work_order_b_production_foundation.py
```

## Expected vs actual

| Check | Expected | Actual |
| --- | ---: | ---: |
| samples | 8 | 8 |
| released after named human / holds | 4 / 4 | 4 / 4 |
| released without named human | 0 | 0 |
| complete custody chains | 7 | 7 |
| unknown / disabled actor refusals | 1 / 1 | 1 / 1 |
| self-approve / collector-release refusals | 1 / 1 | 1 / 1 |
| support window / elevate refusals | 1 / 1 | 1 / 1 |
| support reads allowed | 1 | 1 |
| integration admin / QA erase refusals | 1 / 1 | 1 / 1 |
| QC approved / QC held | 4 / 1 | 4 / 1 |
| unknown device holds | 1 | 1 |
| known device handshakes | 6 | 6 |
| autonomous release refusals | 8 | 8 |
| replay changed records / duplicate effects | 0 / 0 | 0 / 0 |
| production writes / live LIMS / cash_usd | 0 / 0 / 0 | 0 / 0 / 0 |

## Golden hash

- `audit_sha256` `669cf3ea966ee6351ffad46bbc0e2ce6854a10ce290bd6faf380b57910f3ec23`

Replay of the entire scenario creates zero new effects and reprints the same audit hash. Program state stays `NOT_READY`.

## Files

- `runner.py` — working program
- `fixture.json` — synthetic actors, devices, samples, expected counts
- `source.json` — leftover provenance
- `../../aquatrace_work_order_b_production_foundation.py` — thin official command
- `../../test_aquatrace_work_order_b_production_foundation.py` — fail-closed binary
- `../../aquatrace-work-order-b-production-foundation.html` — window, not the product
- `../../p/aquatrace-work-order-b-production-foundation-20260831-01.md` — first leftover receipt

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

