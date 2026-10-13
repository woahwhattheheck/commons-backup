# R04-EXPANDTAX — 16-cell frozen-panel gate verdict

Harness: `~/workspace/build/v4/r04-expandtax/measure_weed_tax.py --mode gate`
(carrier harness; fixed 2026-09-12: maintains the observation step counter the
pinned interpreter reads, without which EOD/`_spawn_weeds` never fires).

- Cells: 16 frozen seeds `2611151001..2611151016`, 30 days, $3000 opening,
  carrot-monoculture BFS sweeper (identical policy across arms).
- Arms: `never` (no BUY_LAND) / `always` (buy when money ≥ price+$400 reserve) /
  `gate` (always-timing + `filter_market_orders` with trailing books).
- Same seeds across arms → paired. Panel is fully deterministic (engine RNG is
  seed-keyed; policy is deterministic) → harness noise = 0 (7 exact ties confirm).

## Results (terminal money deltas per cell)

| comparison | mean | stdev | se | range | +/=/- | cells |
|---|---|---|---|---|---|---|
| dM(gate − always) | **+$938** | $1,162 | $290 | 0..+3,689 | 9/7/0 | 16/16 stable |
| dM(gate − never) | −$2,928 | $1,623 | $406 | −7,281..−1,052 | 0/0/16 | 16/16 stable |
| dM(always − never) | −$3,866 | $2,176 | $544 | −9,042..−1,052 | 0/0/16 | 16/16 stable |

- Engagement: gate altered BUY_LAND *timing* on 9/16 cells (land counts equal —
  both arms buy 2 quadrants; the gate delays unjustified purchases, shrinking
  the weed-exposure window). 0 cells where the gate spent more than `always`.
- `always` arm: mean $2,441 (2.00 quadrants). `gate`: mean $3,379 (2.00).
  `never`: mean $6,307 (0).

## Verdict

Significance threshold max(3·SE=$870, 2·|control|=$0, floor=$5,000) = $5,000.
|$938| < $5,000 → **below the headline bar: MICRO-EDGE, stack it.**

- Positive edge vs naive expansion (+$938, zero harm cells) — the gate's
  mechanism (withhold/delay BUY_LAND until trailing books clear weed tax +
  amortized unlock) is proven on the proxy panel.
- The gate does NOT beat hyper-dense never-expand (−$2,928) under this
  saturated single-farmer sweeper: the policy cannot exploit new tiles, so any
  expansion is pure cost. Honest limitation: the gate's `E` (trailing
  $/planted-tile) overstates *marginal* new-quadrant value for saturated
  policies. On the real v4 router (hands, real marginal capacity) this
  mispricing shrinks — **re-gate on tree-v4base before any activation**.
- No kill: the edge is real, deterministic, and fail-closed (OFF = byte-identical).

## Disposition

File to the serial merge queue as a stacked micro-edge (default OFF, evidence
only — no runtime activation). Next: tree-v4base re-gate with the composer-owned
trailing-books feed; if the v4 router's marginal capacity makes `E` honest, the
gate may graduate to headline.
