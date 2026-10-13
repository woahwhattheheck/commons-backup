# Complete bounded interval-family result

## Outcome

The source-bound scan reproduced all **64/64** committed `consumer-history-v2` terminal families with the exact frozen source before applying the current shared-capacity refinement and interval-family consumer.

The new consumer passed **12/12** focused methods. It enumerates every feasible integer vector under one shared shed-capacity bound and explicit slot/operating-stock hypotheses, or returns no scenarios with a named limit. Marginal endpoints are never combined independently.

## Retained-bank result

- Original exact-history status: **40 ready / 24 insufficient joint history**.
- Every record has all five same-phase interval windows after shared-capacity tightening.
- Complete interval enumeration is ready for **28** records; all 28 were already exact-history ready.
- **36** records exceed the 32-vector budget and return `interval_vector_limit` with no partial scenarios.
- All **24** exact-history-incomplete records hit that limit: 10 at the first lag and 14 at the second lag.
- Another 12 already-ready records exceed the limit only when extra censored lags are added; their existing exact family remains the preferred complete family.
- For all 40 exact-history-ready records, restricting the interval consumer to the exact historical lags reproduces the same economic `shed` and `market` scenario inputs.
- Newly ready records: **0**.
- Terminal-input or selector executions required: **0**.

This is a usable fail-closed mechanism and a measured explanation of the remaining coverage boundary. It does not support a policy/default change or a larger scenario budget by itself.

## Evidence

GitHub Actions run `34197309955` completed successfully. Artifact `10044390347` has provider digest `159eb2aa83a008b121f62db01d332c9cb8eca29031644382c5309527140545d7`.

The generated full per-record scan and test log are preserved in Bryce Library as `/TITAN-BIRCH-interval-history-scan-20260908.zip` (`libfile_2f673b99b41c819190594ca098f4cfe3`).

## Source boundary

- Frozen history-v2 archive: `75740d430c8d137ad4074432f47b7480df1f6864b03e84a367c7e068d27f51ba`.
- Frozen history source ref: `2fc1418f3724ac09232e35a2a583414ce0ee8f84`.
- Current shared-capacity bridge Git blob: `7967fb43c64bc3154fe7da609497873163c773eb`.
- Inputs: committed `history_on-*.json` records only.

No actor, game, engine transition, trace decompression, current rival action, private stock, seed, provider call, canonical package, policy, or default was changed or invoked.

## Reproduce

```bash
python -B revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/interval-family/test_interval_family.py -v
python -B revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/interval-family/scan_bank.py --output /tmp/history-v2-interval-family
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
