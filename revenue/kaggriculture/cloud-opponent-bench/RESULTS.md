# Measured lean20 public-opponent result

Measured on 2026-09-07 with the pinned official interpreter at
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, evaluator SHA-256
`e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c`,
and the already selected lean20 candidate SHA-256
`d9487c031b50ede06a706acc8bcb40e0b5a681d9b5e92c1a1a96492b26c2dd62`.
Every game completed 719 action rounds without an agent, engine, protocol or
timeout failure. Both first-game replay checks matched exact scores and trace.

| Phase | Public opponent | Games | lean20 W/T/L | Mean lean20 cash margin |
|---|---|---:|---:|---:|
| Development | Kaito v43 | 6 | 0/0/6 | -39,767.667 |
| Development | Igor Multi-Route | 6 | 0/0/6 | -43,536.833 |
| Reserved validation | Kaito v43 | 4 | 0/0/4 | -28,012.500 |
| Reserved validation | Igor Multi-Route | 4 | 0/0/4 | -39,777.500 |

## Per-game final cash and runtime

Candidate seat is rotated for every opponent/seed pair. Runtime is full game
wall time; max call is the candidate's maximum child-reported decision time.

| Phase | Opponent | Seed | Candidate seat | lean20 | Opponent | Wall s | Max call ms | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| dev | Kaito | 9000011 | 0 | 36,567 | 82,723 | 1.581 | 2.379 | complete |
| dev | Kaito | 9000011 | 1 | 36,734 | 82,964 | 1.478 | 1.051 | complete |
| dev | Kaito | 9000049 | 0 | 40,957 | 71,680 | 1.789 | 6.455 | complete |
| dev | Kaito | 9000049 | 1 | 40,957 | 71,680 | 1.545 | 2.620 | complete |
| dev | Kaito | 9000061 | 0 | 29,781 | 72,180 | 1.545 | 1.540 | complete |
| dev | Kaito | 9000061 | 1 | 29,797 | 72,172 | 1.590 | 1.740 | complete |
| dev | Igor | 9000011 | 0 | 36,352 | 94,495 | 1.414 | 1.185 | complete |
| dev | Igor | 9000011 | 1 | 39,659 | 93,253 | 1.405 | 1.899 | complete |
| dev | Igor | 9000049 | 0 | 36,143 | 73,137 | 1.602 | 2.344 | complete |
| dev | Igor | 9000049 | 1 | 36,143 | 73,137 | 1.703 | 2.596 | complete |
| dev | Igor | 9000061 | 0 | 73,220 | 110,968 | 1.681 | 3.902 | complete |
| dev | Igor | 9000061 | 1 | 73,220 | 110,968 | 1.584 | 2.005 | complete |
| validation | Kaito | 9000077 | 0 | 49,345 | 93,467 | 1.694 | 4.965 | complete |
| validation | Kaito | 9000077 | 1 | 49,345 | 93,467 | 1.804 | 3.312 | complete |
| validation | Kaito | 9000091 | 0 | 91,152 | 103,055 | 2.079 | 4.316 | complete |
| validation | Kaito | 9000091 | 1 | 91,152 | 103,055 | 1.887 | 1.561 | complete |
| validation | Igor | 9000077 | 0 | 33,535 | 87,569 | 1.608 | 3.690 | complete |
| validation | Igor | 9000077 | 1 | 33,535 | 87,569 | 1.486 | 2.259 | complete |
| validation | Igor | 9000091 | 0 | 83,795 | 109,316 | 1.844 | 3.659 | complete |
| validation | Igor | 9000091 | 1 | 83,795 | 109,316 | 1.893 | 6.087 | complete |

Candidate peak RSS was 21,888 KiB in every game. Source and engine preparation
were networked; all games were offline. The local raw report SHA-256 values were
`a71494a076edf1757ada7786926a6a2fee5e270c788ebce5d0d2fd60e570cfbc`
(development) and
`3c4c11dac37a41a9379f463a445047b7b5e1137359a9308f2716e239cb364d41`
(validation). Hosted workflow artifacts retain their own full raw reports.

## Actionable conclusion

The public panel is materially stronger than lean20 on these five fresh seeds:
lean20 lost all 20 both-seat games, with no result depending on a crash. Treat
Kaito v43 and Igor Multi-Route as minimum development gates for TITAN. A
candidate that only beats Euler28, compact22, or the official starter is not
ready for promotion. This evidence does not establish leaderboard rank,
universal dominance, a submission, an award or a payment.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
