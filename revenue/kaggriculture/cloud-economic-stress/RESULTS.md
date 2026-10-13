# Results

Source: integrated selected candidate PR #9997 / main `b15af384…`, archive
SHA-256 `95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`.
Engine: upstream `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, package 1.32.7,
artifact `10005621438`, ZIP SHA-256
`06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`.

## Natural runtime and guarded equivalence

Development seeds 9922001–9922008, both seats versus intact Arlene:

| arm | games | W/T/L | mean own | mean rival | timeout/error | peak call | max game p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| natural | 16 | 15/0/1 | 74,984.1875 | 74,671.75 | 0/0 | 375.84 ms | 72.02 ms |
| 1-second guard | 16 | 15/0/1 | 74,984.1875 | 74,671.75 | 0/0 | 465.46 ms | 64.61 ms |

Every guarded game is action/cash-equivalent to its natural control. Natural
trajectories reached all requested economic families. Per-game counts ranged:
near-full shed plus multiworker carried/pending stock 8–55; marginal-cash orders
50–61; a market product at the $1 floor 88–311; terminal sale/arrival 24–25.
These predicates are intentionally broad discovery labels; the raw rows preserve
the actual action, cash, shed, carried stock, worker count, price and timing.

Seed 9922003 is the only loss: seat 0 earns 86,270 versus 86,710 (−440), while
seat 1 earns 87,229 versus 85,808 (+1,421). At reached step 683, price floor is
$1, shed/carried stock is 32/32, and the ordered transform clamps `SELL MILK 12`
to 6. A controlled transform-stage timeout there returns the exact producer
action; in both seats own cash falls $55, rival cash rises $75, and margin worsens
$130. The pair remains 1W/0T/1L.

## Terminal production-stage timeout and repair

Seed 9922005 naturally wins by only $8 in either seat (116,969 versus 116,961).
A deliberate one-second overrun before producer selection on final decision 718
made the generic PASS fallback skip 65 carried units and the final market:
both games became losses, 113,352 versus 117,066 (−3,714). Relative to natural,
own cash changed −3,617 and rival cash +105: a −3,722 margin consequence.

The scoped repair uses legal engine `DROP`, not one-product `PLACE`: all products
from each already-adjacent worker transfer in observed inventory order, then every
positive shed product is sold. On the same two games, the forced-timeout arm is
117,027 versus 116,886 (+141), 2W/0T/0L. This restores the missed liquidation;
its +133 margin over the natural controller is an order interaction in this case,
not a general policy claim.

Fresh development seeds 9922009–9922012, both seats, compare natural control with
one forced final-selection timeout handled by the repaired fallback:

| arm | games | W/T/L | mean own | mean rival | timeouts | errors |
|---|---:|---:|---:|---:|---:|---:|
| natural | 8 | 8/0/0 | 79,202.75 | 78,928.25 | 0 | 0 |
| repaired forced timeout | 8 | 8/0/0 | 79,263.75 | 78,849.25 | 8 | 0 |

The repair preserves all eight wins and improves mean margin by 140 in this small
development panel. No held bank was designated, no public opponent panel was run,
and no Kaggle upload or notebook change occurred.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
