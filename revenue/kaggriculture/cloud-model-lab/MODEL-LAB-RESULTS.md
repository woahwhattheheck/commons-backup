# Model lab: E4B proposals over the intact Arlene baseline

Substrate: `../cloud-frontier-policy/next-panel/vendor/arlene.py`, sha256
`1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`, Apache-2.0,
notices retained in place. The source is referenced by pinned hash and never
copied or altered. Engine pin `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

Lane boundaries observed: route-tail selection is LARK's (PR9841, carrot-demand);
sequential shed projection, capacity and production-stock reservation in Arlene
are LARK's; next-hand investment planning is FLORA's; Breaking-the-Tie v12 and
seeds 9600107/9600121 are SORREL's. Nothing here rebuilds any of those.

## What the model produced

E4B authored the OPEN slots of 60 real Arlene turns -- the slots Arlene's own
`_noop` predicate says the engine will ignore -- under `codec.slot_regex`, one
alternation per open slot built from that unit's engine-derived admissible set,
with PASS always expressible.

| | |
|---|---:|
| cards | 60 |
| decoded | 32 |
| syntax rejections | 28 |
| slots authored | 32 |
| chose PASS | 0 |
| engine acted on the choice | 32 |
| turns that disturbed a route slot | 0 |
| mean inference | 15.2 s |

All 28 rejections are the same engine failure,
`RuntimeError: litert_lm_conversation_send_message failed`, on the cards whose
admissible sets produce the largest regexes (FEED, COLLECT_FERTILIZER). That is a
constrained-decoding limit in litert-lm 0.16.1, not a model failure.

Compiled table, provenance `model`, no hand-authored entry mixed in
(`results/motifs-model-slot.json`, sha256 `46cc3fd2ba4e...`):

| id | op | support | precondition |
|---|---|---:|---|
| s001 | WATER | 28 | own plant, `watered_today` false, `unwatered_run` 0 |
| s000 | CARE | 4 | own animal, `cared_today` false, `fed_today` false |

The four CARE rows are the interesting ones: those cards offered FEED and the
model declined it every time. FEED spends a carried WHEAT; the per-seat order
ledger later showed one such FEED at d28h23 costing exactly $41 of WHEAT that was
then never sold, with the rival unchanged.

## Rating-relevant result first: W/T/L

Only win/loss/tie changes ratings; coin margin magnitude does not. Candidate
against its own control, per paired game:

| arm | authored | control W/T/L | candidate W/T/L | pairs changed |
|---|---|---|---|---:|
| engine-derived controls | hand | 4/4/0 | 4/0/4 | 4 |
| upkeep only | hand | 4/4/0 | 4/0/4 | 4 |
| CARE only | hand | 4/4/0 | 4/4/0 | **0** |
| E4B slot motifs (development) | model | 4/4/0 | 4/4/0 | **0** |
| E4B slot motifs (RESERVED) | model | 4/4/0 | 4/4/0 | **0** |
| one animal bought and installed | hand | 4/4/0 | 4/0/4 | 4 |

Every changed pair is a TIE LOST IN AN ARLENE MIRROR, where the control margin is
exactly 0 and any perturbation at all breaks it. **Against a different opponent
(Apex) no arm changed a single win or loss.** So in rating terms the arms that
spend something are harmful only through self-play ties, and the model table is
neutral -- confirmed on reserved seeds it was frozen before.

Own cash and margin below diagnose why; they are not the rating.

## Paired full-game scores

Candidate and control differ by the overlay and nothing else: same seed, same
seat, same opponent, same intact baseline. Own cash and own-minus-rival margin are
tracked separately. Every pair was run with the end-of-day RNG path recorded, and
in every pair below the two arms share an identical path on all 30 days, so none
of these differences is a different town.

| table | authored | panel | mean d_own | mean d_margin | fills |
|---|---|---|---:|---:|---:|
| engine-derived controls | hand | dev, 8 games | +6.2 | −128.2 | 140 |
| upkeep only (CARE/FEED/WATER) | hand | dev, 8 games | −38.2 | −39.0 | 20 |
| CARE only | hand | dev, 8 games | +0.0 | +0.0 | 12 |
| **E4B slot motifs** | **model** | dev, 8 games | **+0.0** | **+0.0** | 56 |
| **E4B slot motifs** | **model** | **reserved 9700003/9700019, 8 games** | **+0.0** | **+0.0** | 32 |

## Position safety

`_noop` answers whether the engine ignores an op *on the tile the worker is
standing on*. Once a worker is walked away it is answering about the wrong tile,
and the route's own work at the home tile is silently skipped. Measured cost of
ignoring that: −105,072 own cash on one seed over 1,571 such steps, and −34,576
after adding a return-to-home leg. The sound admission is a literal-PASS window
read off the tape, since a PASS is a no-op wherever the worker stands, re-read
live each turn because a checkpoint switch replaces the suffix.

Per game:

| seed | free slots | board has a target | reachable two-way | reachable one-way |
|---|---:|---:|---:|---:|
| 9600011 seat 0 | 563 | 562 | 265 | 321 |
| 9600029 seat 0 | 670 | 669 | 266 | 323 |

Two-way is out, act, and back to the tile the route left the worker on, inside a
literal-PASS window. One-way needs no return: the end-of-day refresh drops every
carried inventory into the shed regardless of position, respawns the farmer and
disbands the hands (873-882), so a collection finishing inside the day banks
itself and the displacement ends at the reset. It requires instead that the tape
want nothing from that worker for the rest of the day, and it is excluded on the
final day, whose close has no turn left to sell into.

The worker lane is therefore NOT closed for lack of reachable work.

## The candidate: harvest an animal about to overflow its output cap

`_daily_refresh_animals` writes `yield_units = min(max_held, yield + base +
bonus)` (827), so a unit produced onto an animal already at its cap is destroyed
at that refresh. No "does the route harvest this tile eventually" test can see
it: the units are gone before any later harvest arrives. Measured on the intact
baseline, seed 9600011 loses **42 units over 24 refreshes** (38 EGG, 4 MILK),
about $1,732 at final prices, with tile (4,1) alone losing 12; seed 9600029 loses
4 MILK. Part of that is not recoverable by harvesting earlier -- some events have
`yield_before` 0 and overflow on an accumulated care bonus instead -- and the
recoverable part is the subset already sitting at `max_held`.

`CapChooser` takes only the reachable animal that would lose the most at the next
refresh. HARVEST leaves the animal in place, so taking it early forfeits nothing.
Execution is one-way: the plan finishes inside the day and the end-of-day drop
banks it.

Development panel, 2 seeds x both seats x Arlene and Apex, RNG path identical in
every pair:

| | control | candidate |
|---|---|---|
| W/T/L | 4/4/0 | **6/2/0** |
| pairs changed | | 2, both **T → W**, none to L |
| mean d_own | | +2.0 |
| mean d_margin | | +1.5 |

Seed 9600029 produced zero fills -- no cap-threatened animal was reachable -- so
the intervention does nothing there rather than perturbing a game it has no
thesis about. That is the shape the five rejected arms lacked: they fired
everywhere, this one fires only where the loss is.

Source was then frozen (sha256 in `results/cap-candidate-frozen.txt`) and run on
seeds 9700037 and 9700053, which it had never seen:

| panel | control W/T/L | candidate W/T/L | changed | mean d_own | mean d_margin |
|---|---|---|---|---:|---:|
| development 9600011/9600029 | 4/4/0 | **6/2/0** | 2, both T→W | +2.0 | +1.5 |
| **RESERVED 9700037/9700053** | 4/2/2 | **6/0/2** | 2, both T→W | **+67.8** | **+67.0** |

Sixteen paired games. Four ties converted to wins, **no win or tie ever turned
into a loss**, own cash improved or held in every pair, and the two arms share an
identical end-of-day RNG path in all sixteen. Reserved per-pair own-cash deltas:
+106, +114, +106, +114, +26, +16, +26, +34.

Only one plan in five completes, so the captured amount is well short of the
$1,732 the cap destroys on 9600011. Raising that is a NEW candidate and needs new
development seeds; it is not a tuning pass on these.

Capacity is not the gap either: over full games Arlene strands **no** animals --
final shed and carried are both empty -- and holds an animal with a matching empty
structure on only 50 of 719 turns, peak 3. Its own `_noop` already catches 563-670
engine-ignored slots per game and misses 10-11.

## The shared price channel, measured

With the RNG path identical and only twelve of the seat's own worker slots
changed, the per-seat order ledger shows the rival gaining $195 on **identical
unit counts**: the same 261 MILK for $174 more, the same 348 FERTILIZER for $31
more, the same 64 FERTILIZER bought for $5 more. The seat itself gained $133 on
the same 261 MILK and lost $42 on WHEAT.

Nobody sold more. Changing when the seat transacts reorders the shared curve, and
the lift went more to the rival than to the seat. In a mirror that is a margin
loss even while own cash rises. This is a measurement of the channel on one pair,
not a general claim about its size.

## Open finding for the capital lanes

The largest inefficiency still visible in the trace is on the capital side, not
the worker side. Seed 9600029 finishes with **nine structures the route built and
never stocked**, at 70,334 own cash against 132,726 on 9600011, with zero animals
ever stranded -- so the route never buys for them.

`structure_value.py` prices that with a single one-off purchase at an observed
state, installed under the position-safe rule, against an otherwise identical
control:

| seed | buy | installed | d_own | d_margin |
|---|---|---|---:|---:|
| 9600029 | COW at step 255 | yes | **+669** | −2,861 |
| 9600029 | COW at step 626 | yes | −399 | −399 |
| 9600011 | COW at step 200 | yes | −153 | −682 |
| 9600011 | COW at step 255 | yes | −119 | −362 |

Completed against both parents, at the buy step that installs on every pair:

| seed | opponent | d_own | d_margin |
|---|---|---:|---:|
| 9600011 | Apex | −257 | **+657** |
| 9600011 | Arlene | −119 | −362 |
| 9600029 | Apex | −176 | **−3,201** |
| 9600029 | Arlene | **+669** | −2,861 |
| | **mean** | **+29.2** | **−1,441.8** |

**Rejected.** +669 own cash is sixteen times the whole idle-slot range and lands
exactly where the audit said it would -- on the seed whose structures go unfilled
-- but margin is negative on three of four pairs and the mean is −1,442. Note the
shape: own cash moves in the hundreds while margin moves in the thousands, and
its SIGN flips by opponent and by seed. One $400 purchase takes seed 9600029's
margin against Apex from +5,129 to +1,928.

## What five rejected arms have in common

| arm | authored | mean d_own | mean d_margin |
|---|---|---:|---:|
| engine-derived controls | hand | +6.2 | −128.2 |
| upkeep only | hand | −38.2 | −39.0 |
| CARE only | hand | +0.0 | +0.0 |
| E4B slot motifs | model | +0.0 | +0.0 |
| one animal bought and installed | hand | +29.2 | −1,441.8 |

Across every arm the direct production effect is worth hundreds of dollars of own
cash, and the margin swing is up to an order of magnitude larger and points
wherever the reordering of the shared price book happens to land. With the RNG
path held identical and the per-seat order ledger showing unchanged unit counts,
the channel is not supply and not a different town: it is WHERE in the shared book
the seat's transactions fall.

The implication is for the lane that owns sales, not this one: on this substrate
margin is dominated by transaction placement rather than by production volume.
This lane holds the instrument that measures it -- paired arms with an identical
recorded RNG path plus per-seat order attribution -- and is putting a sensitivity
profile of that channel behind it rather than another production overlay.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
