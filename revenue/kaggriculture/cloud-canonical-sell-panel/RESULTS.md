# Results

## Decision result

Across 16 independent development seeds and both seats, canonical DEFAULT scored
**27 W / 4 T / 1 L** against exact frozen SELL: 32/32 games completed, tie-aware
score `0.90625`, mean cash margin `+$210.625`, and median margin `+$240`.
Candidate cash totaled `$2,713,097` versus `$2,706,357` for frozen SELL. There
were no timeouts, invalid actions, crashes, or engine errors.

At the seed-cluster level, 13 seeds were W/W, two were T/T (`9922013` and
`9922028`), and one split W/L (`9922023`). No seed was L/L. Stage 1 was
6 W / 2 T / 0 L on four seeds; the source-fixed 12-seed extension was
21 W / 2 T / 1 L.

| Seed | Seat 0 | Seat 1 | Candidate margins |
|---:|:---:|:---:|---:|
| 9922013 | T | T | 0, 0 |
| 9922014–9922016 | W | W | +240, +240 each |
| 9922017 | W | W | +357, +133 |
| 9922018–9922022 | W | W | +240, +240 each |
| 9922023 | W | L | +876, −386 |
| 9922024–9922027 | W | W | +240, +240 each |
| 9922028 | T | T | 0, 0 |

## The one loss is not an integration regression

The loss is exactly reproducible at seed `9922023`, candidate seat 1: DEFAULT
finished at `$56,109` and frozen SELL at `$56,495` (−$386). A diagnostic replay
matched both terminal cash values and the original full trace SHA-256
`3d68450e97a956e3b258af71ded86ca66d46bbf0bac9af0877c0a040c886c5e3`.

Frozen-vs-frozen self-play on that same seed produces the inherent seat result
`[$56,495, $55,859]` in both role orderings: seat 0 leads by $636. Relative to
that exact source baseline, DEFAULT raises seat-1 cash by $250 (`55,859→56,109`)
but does not erase the seat disadvantage. In the paired seat-0 game DEFAULT
raises cash by $240 (`56,495→56,735`) and wins by $876. Therefore the recorded L
is a real W/T/L consequence of seat interaction, while the enabled increment is
cash-positive in both source-conditioned comparisons. No source repair is
supported by this reproducer, and no integration defect was sent upstream.

## Production funding hook

The shipped entry—not a test-only `Features` override—loads config SHA-256
`a186bec191d4e11908ffd805e86203e16f3ee30804c61887afd629af2e72470f`
with `consumer=frozen`, `seed=true`, and `funding=true`. On the reached official-
engine seed-9922023 loss trajectory at step 600, `main.py::agent` called
`select_seed_queue` exactly once. Its actual selected queue contained
`BUY_SEED WHEAT 17` followed by seven HIRE orders; the returned queue changed
only that seed quantity to 1 and preserved all seven HIREs. The funding report
was certified, used no rival-private state or extra controller call, and saved
$160 of current-market cash. The independent pre-panel probe on already-consumed
seed `9922005` likewise counted one call and reduced WHEAT `17→2`.

## Runtime observations

The slowest canonical DEFAULT decision was `0.523061 s` (seed `9922022`, seat 0)
and its corresponding parent-observed RPC time was `0.579572 s`, below the real
1.0-second deadline. Frozen SELL's slowest child decision was `0.186690 s`.
Peak observed actor RSS was `24,428 KiB`. These are per-game process observations
from this Work VM; they are not extrapolated from a warm call and do not assert
an independently enforced 1.6-CPU cgroup. Two completed control actors contain
known implausible `/proc` aggregate CPU samples, so aggregate CPU totals are not
used; child decision/RPC maxima, completion status and RSS remain recorded raw.

This panel establishes only the stated source-conditioned head-to-head result.
It does not establish leaderboard score or rank.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
