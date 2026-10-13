# T15 measured result

The exact solver and persistent complete-plan transform are runnable. Actual
official-engine tables have positive finite-table mixtures and pure alternatives
with minimum relative receipts below zero. Full-game selections use pure
endpoints; no nondegenerate mixture was selected. Frozen SELL remains selected.

## Versioned full games

| Version/panel | Newly executed | Comparison controls | Result |
|---|---:|---|---|
| v1 development | 72 | Included | Four pure endpoint choices add2 own cash/0 rival each; two SELL ties become wins |
| v1 held | 48 | Included | 45 complete; three pure-arm games end at the RPC deadline; no activation |
| v2 development | 48 | 24 unchanged v1 baseline games reused | Pure/mixed have no activation; exact control traces and cash |
| v2 held | 48 | Included | All48 complete; pure/mixed endpoint choices produce -4 own cash/0 rival per Apex seat; no W/T/L changes |

Total216 unique game attempts,213 complete719-decision episodes. Original
T11/T12 seeds and completed panels were not replayed. Development9872001/19/37;
v1 held9872101/119; v2 held9872201/219. Both seats face unchanged Arlene, Apex,
frozen SELL and the accepted Arlene sale-cadence stress. Actual responsive
opponents run in isolated processes; no future rival orders enter the policy.

V2 comparison has120 complete games, including24 reused baseline controls.
Each arm is18W6T in development and12W4T held: all Arlene/Apex/cadence games
win and all SELL games tie. V2 pure has4 held activations, mixed2; all are pure
endpoints. No nondegenerate mixture occurs in either version's full games.
All own/rival cash pairs and complete trace identities are in RESULTS.json.

## Source correction and causal witness

V1 source is4d97474b0188b0373be1b52b610c0114ceb033c8, freeze
cf469ff4c5da39efdf7a995161a3dc071aee4903eea450f001276fb6c357ec94.
At development step505 it delays EGG2 to513. Its label-based history selection
omits T12 streams whose identical shift0 version was deduplicated in favor of
the first shift-1 label. V2 retains whole stream values regardless of that
surviving label; T12's accepted model and data are unchanged.

The repair was frozen before any v1 held outcome was inspected, and v2 uses
new held seeds. V2 freeze is
f2204526057eb4c07abebd8477c6de94372c05ef69e08d9d9698e30aa03fce7a.
No source/parameter adjustment followed v2 held results.

`causal_case.py` reconstructs only the recorded past windows from that reached
development decision: latest training timestamp489, decision505. Restored
streams include EGG12 at505/506, rather than only the standing stress quantities
up to4. The late-sale worst expected margin becomes0 from2. Both pure and
mixed selectors retain the baseline under their positive-gain criteria.
The corrected32-column table matches the official interpreter in both seats.
The actual v1 gains remain preserved; they are not a mixing result.

## Engine discrimination and runtime

Eleven tables match7,074 serialized official transitions, both seats, with
full lot fills and town consumption after market. Ten are constructed market
regimes; one is the causal table from the reached development observation.
For TOMATO8/I10080/PIZZA_SHOP+FARMERS_MARKET, baseline2-now/6-end versus
4-now/4-end and8-end yields exact weights4/7,3/7 and worst expected relative
gain2/7 across28 supplied streams. Each pure alternative has negative columns.
The earlier strawberry two-column example yields1/5, but adding a legal paired
rival sale hurts both alternatives by1 and restores baseline. No omitted
scenario distribution, real-world income or whole-game equilibrium is claimed.

Eleven focused test groups pass, including80 independent LP oracle comparisons,
same-information-set invariance, fixed action positions, constituent
feasibility, cash/stock reservations, retries, commitment completion, and
T12's actual stream-label deduplication case. Production uses standard library.

V2 mixed peak policy396.38ms, RPC404.11ms, cold policy82.51ms and episode11.27s.
V2 pure peak policy507.12ms, RPC510.80ms and episode11.85s. Evaluator limits are
1s action RPC,120s episode wall,0 overage. V1's three held pure-arm games ending
at the RPC deadline remain in the ledger: two candidate calls and one Apex call.

Standalone archive80,064 bytes, SHA256
4902533eec3df6a3049d0da31e6c4fc9eae74e53901914682739fafdc0861dbd.
All29 members are hash-verified. Two fresh constructed initial-seat observations
match direct source, source official loader and archive official loader;
maximum archive first call26.32ms. No extra full game or held replay was used
for packaging. EVIDENCE.json records every retained compressed report's hash.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
