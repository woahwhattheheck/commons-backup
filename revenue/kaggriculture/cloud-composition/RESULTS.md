# KAG-COMPOSE measured results

## Development (three seeds, both seats)

| Candidate | Opponent | W-L | Mean coin margin |
|---|---|---:|---:|
| ROWAN | Kaito v43 | 0-6 | -46,489.00 |
| ROWAN | Igor MultiRoute | 0-6 | -66,104.00 |
| dispatch_pipeline | ROWAN | 2-4 | -1,470.83 |
| dispatch_pipeline | SORREL pipeline | 6-0 | +3,741.50 |
| dispatch_pipeline | lean20 | 4-2 | +1,041.67 |
| dispatch_pipeline | Kaito v43 | 0-6 | -57,551.17 |
| dispatch_pipeline | Igor MultiRoute | 0-6 | -50,071.50 |
| dispatch_balanced | ROWAN | 4-2 | +789.17 |
| dispatch_balanced | SORREL balanced | 6-0 | +3,716.83 |
| dispatch_balanced | lean20 | 4-2 | +3,695.00 |
| dispatch_balanced | Kaito v43 | 0-6 | -57,867.50 |
| dispatch_balanced | Igor MultiRoute | 0-6 | -53,717.50 |

`dispatch_balanced` passed the predeclared gate. Its public-panel floor
(-57,867.50) is above ROWAN's (-66,104.00). `dispatch_pipeline` failed the
component gate and was rejected before validation.

## Reserved validation (two seeds, both seats)

| Opponent | W-L | Mean coin margin |
|---|---:|---:|
| ROWAN | 2-2 | +837.25 |
| SORREL balanced | 4-0 | +2,124.50 |
| lean20 | 4-0 | +5,324.75 |
| Kaito v43 | 0-4 | -57,273.50 |
| Igor MultiRoute | 0-4 | -75,324.75 |

All 92 games reached the 719-action-round terminal state with zero candidate or
opponent failures. Deterministic replay passed in all four reports. The results
support a composition improvement over its two internal components on this
small split; they do not establish public-opponent parity, hosted rank, a valid
Kaggle submission, acceptance, award, or payment.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
