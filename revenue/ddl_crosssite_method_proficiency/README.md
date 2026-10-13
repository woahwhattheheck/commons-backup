# ddl-crosssite-method-proficiency-lims-01

Working program for **DDL, Inc. / Suzette Glennon**: cross-site controlled-method + proficiency-comparison across Minnesota, California, and New Jersey under one QMS.

The runner is the product. `python3 ddl_crosssite_method_proficiency.py` performs intake → facility scope → controlled method/version → instrument/operator linkage → paired-site comparison → exception review → evidence pack → HOLD/release. Tests prove that program. The HTML window is not the product.

Exact posted 120/40 fixture from Slack `#build-demand` `1788149883.630329`. No live LIMS. No accreditation claim.

## Boundary

Synthetic / read-only adapters (QMS, LIMS, instrument, report). No production writes. No automatic release. Named human required before any report release. `cash_usd=0`. STATE remains **HOLD / BUILD-AND-VERIFY**. No outreach. No phone. No personal email.

Cite, do not remint: `westpak-scope-capacity-routing-lims-01` (PR 6815 merge `fa0fc2f8` blob `f282a9ed`), `highpower-ssf-receiving-gate-lims-01`, Wadsworth, Sharp, `pcl` blob `6484c590`, `canyon` blob `a4ea30a9`, savant-fe8 PR 6722, weck, kincell, organabio, elevatebio, made-scientific, roslinct. Off billings-bid-1421, SKUs 1–7, AquaTrace, PR 6813, fire_action, $5 tip.

## Official command

```bash
python3 ddl_crosssite_method_proficiency.py
python3 revenue/ddl_crosssite_method_proficiency/runner.py
python3 test_ddl_crosssite_method_proficiency.py
```

The no-arg command writes `state/journal.json` plus `receipts/{run,studies,holds,comparisons,evidence,audit,replay}.json`.

## Expected vs actual

| Check | Expected | Actual |
| --- | ---: | ---: |
| studies | 160 | 160 |
| valid | 120 | 120 |
| blocked | 40 | 40 |
| MN-CA / CA-NJ / MN-NJ | 40 / 40 / 40 | 40 / 40 / 40 |
| exact controlled method/version | 120 | 120 |
| blocked with expected reason | 40 | 40 |
| paired-site truth table match | 120 | 120 |
| comparison flags expected | 120 | 120 |
| facility/instrument/operator/method/report linkage | 120 | 120 |
| released without named human | 0 | 0 |
| released after named human | 120 | 120 |
| replay duplicate study / evidence events | 0 / 0 | 0 / 0 |

## Golden hash

- `audit_sha256` `c6259d48907f9b27477e52fedaff65558f3153f81b343de0c2d86a695fce308a`

Replay of the entire 160-study corpus creates zero duplicate study or evidence events and reprints the same audit hash.

## Files

- `runner.py` — working program
- `fixture.json` — exact 160/120/40 contract
- `source.json` — leftover provenance
- `../../ddl_crosssite_method_proficiency.py` — thin official command
- `../../test_ddl_crosssite_method_proficiency.py` — fail-closed binary
- `../../ddl-crosssite-method-proficiency-lims.html` — window, not the product
- `../../p/ddl-crosssite-method-proficiency-lims-01.md` — first leftover receipt

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

