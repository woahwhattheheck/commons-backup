# oregon-brewlab-sample-report-reconciliation-lims-01 receipt

State: TESTED
Binary: `python3 test_oregon_brewlab_sample_report.py`
CLI: `python3 oregon_brewlab_sample_report.py`

| check | expected | actual |
|---|---|---|
| input rows | 120 | 120 |
| READY once | 96 | 96 |
| held | 24 | 24 |
| HOLD codes | 8 FORM_CONTAINER_MISMATCH + 6 DUPLICATE_ID + 5 WARM_MICRO_VDK + 5 INSUFFICIENT_VOLUME | exact |
| duplicate jobs | 0 | 0 |
| staged reports | 96 | 96 |
| released reports (autonomous) | 0 | 0 |
| replay added jobs | 0 | 0 |
| fixture_sha256 | e966c3143f9b8edebac7547e46949d7d6444636ecfd4256ae896c081524a09cf | match |
| catalog_sha256 | 657d60b6f1e1b8ccfe4358950fa93cf21fd741fc714fd3444a6fe2d030f44613 | match |
| audit_sha256 | bf5dc68f8f07262e9f195441a84ca54a56d8d86e40e572e9b8768786a7f930ca | match |
| report_digest | 2e22f1f918744479a2e00b420323f9de02a7d1936e8feb0f0e323efd4bd9ef3a | match |

Buyer: Oregon BrewLab / Dana Garves. Form/container reconcile, public 4 oz / 12 oz and micro-VDK cold-chain gates, ASBC routing, QC, report-class, simulated notify, staged human release. Interfaces simulated. No production write, outreach, or automatic release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
