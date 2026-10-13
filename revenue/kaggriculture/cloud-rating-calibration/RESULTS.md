# Calibrated PR9997 strength relative to hosted Arlene

No games were run in this lane. The analysis consumes Claude's per-game output
landed at `ed8868663235fad501cad1174a4b5c2233dd8d38`; PR10005 remains frozen.
The exact PR9997 archive is `95c7bf10…`, and every consumed row names runtime
`9e5e4eb6…`. The opponent in every row is Arlene v14 source `1dc166ae…`, which
is the candidate recorded by the retained 33,908-byte archive `7dcb73bb…`.

The provider identifies submission 56081391 as a 33,908-byte
`submission.tar.gz` named “TITAN — Arlene v14 baseline.” It exposes no remote
content digest. Thus the game-to-retained-source identity is exact, while the
retained-source-to-hosted identity remains conditional on ROWAN/KESTREL's byte
receipt. The analysis never substitutes a generic SELL controller.

## Empirical model and result

The model counts a tie as half a win, applies a half-point/one-game boundary
penalty, and transforms the resulting head-to-head log odds onto the
conventional 400-point Elo scale. Its 95% interval is a deterministic 100,000
draw percentile bootstrap over whole seeds, retaining both seats in every
draw. This groups the intended seed/mirror dependence. It remains conditional
on one matchup and does not remove nontransitivity or opponent-population
shift.

| Split | Seed clusters | Games | W/T/L | Seat 0 | Seat 1 | Elo-scale proxy (95% grouped interval) | Mean cash margin (95% grouped interval) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development | 32 | 64 | 60/0/4 | 30/0/2 | 30/0/2 | +451.4 (+329.1, +650.7) | +203.8 (+155.0, +260.9) |
| Held | 8 | 16 | 13/2/1 | 7/1/0 | 6/1/1 | +305.4 (+128.1, +607.4) | +177.7 (+96.4, +262.4) |

The newest recovered hosted point is 2203.3 at
2026-09-08T01:24:38.364247Z. Its six retained observations from 18:56Z through
01:24Z span 2166.7–2215.4. Combining that temporal drift envelope with grouped
matchup uncertainty gives a development sensitivity band of 2495.8–2866.1 and
a held sensitivity band of 2294.8–2822.8; point-anchored proxies are 2654.7 and
2508.7 respectively. These are explicitly **not Kaggle backend score
intervals**: Kaggle publishes the qualitative rating direction and
opponent-strength dependence, but not the exact backend equation or update
constant.

The held result is the primary out-of-sample estimate and is much wider. The
development result is retained as supporting precision, not relabelled held.
The large Arlene-relative advantage also does not establish general dominance:
in the same landed source-backed panel, frozen SELL beats PR9997 31–9 on
development and 13–3 on held. Frozen SELL has no version-specific hosted
submission/rating binding, so it is a valid relative sensitivity opponent but
not an absolute score anchor.

## Strongest internal opponent and source-family outcomes

Against frozen SELL, all-game empirical outcome probabilities are sharply
reversed: PR9997 is 11/0/53 in development (W/L 17.2%/82.8%) and 3/0/13 in held
(18.8%/81.2%). Whole-seed bootstrap intervals for its win probability are
6.3%–29.7% and 0%–43.8% respectively. The penalized score odds favor frozen
SELL by 4.65:1 in development and 3.86:1 in held. On the arbitrary 400-point
illustration only, PR9997 is -267 (-451, -147) and -235 (-607, -41) relative to
frozen SELL. These are relative matchup quantities, not Kaggle scale values.

| Source family | Split | Games | Empirical W/T/L probability | 95% whole-seed bootstrap W | 95% whole-seed bootstrap L |
|---|---|---:|---:|---:|---:|
| Arlene v14 | Development | 64 | 93.8% / 0% / 6.3% | 87.5%–98.4% | 1.6%–12.5% |
| Arlene v14 | Held | 16 | 81.3% / 12.5% / 6.3% | 56.3%–100% | 0%–18.8% |
| Frozen SELL | Development | 64 | 17.2% / 0% / 82.8% | 6.3%–29.7% | 70.3%–93.8% |
| Frozen SELL | Held | 16 | 18.8% / 0% / 81.3% | 0%–43.8% | 56.3%–100% |
| Compiled Apex | Development only | 32 | 96.9% / 0% / 3.1% | 90.6%–100% | 0%–9.4% |

These are family-conditional empirical expectations. A zero observed tie rate
and its degenerate nonparametric interval do not prove the population tie rate
is zero. Apex was not retained for the 32-seed expansion or held because it did
not discriminate candidate from parent in the preceding panel.

## Rank conclusion

No rank interval is emitted. The recovered pairs—2215.4/rank684,
2166.7/rank762, 2196.5/rank717, 2191.1/rank744, and 2203.3/rank722—are
longitudinal observations of one submission on a moving leaderboard. They are
not a contemporaneous cross-sectional score-to-rank map. The consumer requires
at least three distinct monotone anchors at one timestamp, covers both score
endpoints, and refuses extrapolation.

Eight focused methods pass. They cover grouped W/T/L and ties, incomplete and
duplicate seat rejection, exact source-hash rejection, temporal baseline bands,
same-time rank interpolation, and rejection of longitudinal or extrapolated
rank mappings. `input-development.json` and `input-held.json` retain all 80
terminal cash observations and their runtime source hashes; the original rich
traces remain at the cited source commit.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
