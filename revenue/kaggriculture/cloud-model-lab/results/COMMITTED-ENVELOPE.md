# Committed capacity envelope: accuracy versus looseness

## The question

The fixed-state ablation established that the dated capacity envelope gates a sale
the optimizer has already valued, but not *why* it helps. Two candidates predict
opposite things for the held regression:

- **accuracy** — it dates arrivals correctly, so the optimizer stops withholding
  capacity it will actually have
- **looseness** — `possible_extra_deposits` is a deliberate upper bound over every
  worker against every animal, so it over-reserves, and over-reservation tells the
  profile the shed will be fuller than it will be

This substitutes the producer's **actually committed** arrivals — whole lots at the
exact phase the arrival contract assigns — and changes nothing else. T08's
`conserved_sell_adapter.py` is imported unmodified; only the event source is
swapped for one `receipt_profile` call.

## Case 669 answers it

Same fixed state, selected action, valuation, rival assumption and conserved
inventory:

| arm | plan | engine receipts |
|---|---|---:|
| none | `[[669, 0]]` | 90.0 |
| coarse (reserve 91) | `[[669, 0]]` | 90.0 |
| dated (speculative bound) | `[[669, 3]]` | 642.0 |
| **committed (real arrivals)** | `[[669, 0]]` | **90.0** |

The committed envelope does not unlock the sale. **The gain there is looseness.**
Over-reserving makes the optimizer liquidate earlier to protect capacity, which is
the day-26/27 pattern that sold strawberries at ~12 instead of ~41.

## Development, 9870001 / 9870053 / 9870037

Control is the **selected default**, frozen SELL — not intact Arlene. 12 pairs,
both seats, Arlene and Apex.

| arm | W/T/L | flips | mean d_own | pairs worse | range |
|---|---|---:|---:|---:|---|
| frozen SELL | 12/0/0 | — | — | — | control |
| conserved (speculative) | 12/0/0 | 0 | −128.3 | 4 | −1,116 … +778 |
| **committed** | 12/0/0 | 0 | **+104.5** | **0** | +38 … +142 |

**All three arms are 12/0/0 with not one flip**, so this panel shows no
rating-relevant difference. What it shows is consistency: committed is positive on
every pair, speculative loses 941 and 1,116 on seed 9870001 and gains 778 on 9870037.

## Held, 9870101 / 9870119 — source frozen first

| arm | W/T/L | flips | mean d_own | pairs worse |
|---|---|---|---:|---:|
| frozen SELL | **6/0/2** | — | — | control |
| conserved | **8/0/0** | 2 × L→W | −5.0 | 2 |
| **committed** | **8/0/0** | 2 × L→W | **+117.8** | **0** |

Frozen SELL loses seed 9870119 versus Arlene in both seats (margin −37). Both cap
arms convert those two losses. The committed envelope does it while being positive
on every pair (+91 … +154); the speculative one gives back 298 twice on 9870101
versus Apex.

**Limits.** Two held seeds, eight pairs, and the seats mirror, so four distinct
games; both of frozen SELL's losses are the same seed and opponent. This is a
candidate against a local pinned interpreter and two local opponents, not a
leaderboard result, and no selection has been changed.

## Consumption

```python
from committed_envelope import agent, CommittedCapSell   # agent(obs, cfg)
tx = make_committed_sell(base_owner, snapshot_provider)
committed_events(snapshot, now, end, tpd)   # -> possible_extra_deposits shape
```

`snapshot_provider()` must return `PlanOverlay.producer_snapshot` for the same
observation. A carried lot reserves nothing, because the profile's own projection
already holds it; an aborted errand reserves nothing at all.

## Interface finding

The frozen scheduler indexes `obs['step']` directly, and the engine omits that key
from a seat-1 observation, so a seat-1 game raises `KeyError` before any policy
runs. `sell_arm.py` normalises it in the harness, as Arlene does internally. Same
missing key already reported for `build_arrival_contract`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
