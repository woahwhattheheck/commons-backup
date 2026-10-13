# SELL scheduler: exact engine cases

Executed in this session's Linux cloud container on 2026-09-07. The first ten
discriminating cases passed in 0.793 seconds; the additional runtime-quote parity
case passed in 0.062 seconds. The latter checks 945 quotes across all nine products,
default parameters and six legal price-curve overrides. These are transition and
integration measurements, not leaderboard or policy-strength results.

Run from this directory:

```bash
python -B test_engine_semantics.py
```

The script runs unmodified functions from the preserved official interpreter. Its
last-window case also runs the existing process-isolated Commons evaluator with
two real policy subprocesses for a complete game. Neither the evaluator nor these
tests are the hosted Kaggle runner. All actor scratch stays under this cloud-lab
directory. No service, notebook write, submission, LM or platform installation was
needed.

| Discriminating case | Executed result | Constraint for the scheduler |
| --- | --- | --- |
| MILK inventory 10075, own stock 4 | Receipts $3+$1+$1+$1=$6; market ends at 10076 | Count only quotes above $1 as admitted supply. Floor-price sales still consume stock and pay. |
| Both seats sell 2 MILK at inventory 10000 | Each receives $316; market ends 10004 | Both first units quote $160; both second units quote $156 from the same precommit inventory. |
| Both seats sell 2 MILK at inventory 10075 | Each receives $4; market ends 10077 | Both $3 quotes admit their unit before the next paired quote; one seat's commit cannot rewrite the other seat's already-fixed quote. |
| Own 12 MILK, market 10030, four observed SMOOTHIE_SHOP copies, tick4 | Sell all now: $1026. Sell6, consume, then sell6: $1078. Both end at market10038. | The $52 gain is a conditional batching mechanism with known absorption. Current market runs before this tick's consumption. |
| Same own stock/market; wait while rival may sell24 | Wait/no rival: $1126. Wait/rival24: $522. Sell now paired with rival24: $887. | A rival-supply scenario reverses the waiting preference. Do not label no-rival timing gain robust. |
| Orders SELL7 MILK then SELL7 with stock10 | Exactly10 units sell for $1506 | Later orders share the remaining stock. Never credit14 receipts. |
| Zero cash, stock1 MILK | SELL then HIRE: one hand and $159. HIRE then SELL: no hand and $160. | Keep ordered cash dependencies. Atomic HIRE/BUY_LAND execute before the paired commodity work at their own order index. |
| Step23, shed WHEAT90/MILK10, carried MILK20 | Hold loses20 overflow. Selling10 pays$1506, then EOD admits10 and loses10. Both finish shed100. | Market can make space for the automatic EOD receipt; capacity is shared across all non-seed goods. |
| Step22, same full shed/carried stock, farmer DROP then SELL10 MILK | DROP discards20 before market; sale leaves shed90 | Same-turn market space cannot rescue an earlier overflowing DROP. |
| Step718, shed MILK1, carried MILK3, SELL4 | One unit sells for$160, status DONE, three units remain carried with zero salvage | Only post-unit shed stock can sell. Decision718 is hour22, so no final day29 EOD occurs in this 720-state match. |
| Existing evaluator, BUY1 WHEAT at717 then SELL1 at718 | 719 actions per seat, observed steps0..718, both final cash$3000 | The final executable sale window is718, and unchanged-state roundtrip profit is zero. |
| Runtime `mechanics.market_price` against official engine | 945/945 exact matches; half-dollar examples9.5→10 and8.5→8 | Use exact dollar rounding and configured curves, including defaults and floor. |

The town example uses four already-observed shop copies and no guessed future
shop unlocks. A SMOOTHIE_SHOP consumes one MILK per tick. Single-product shops
consume two units per copy; center consumption is an additional one unit of every
non-fertilizer product on steps divisible by24. Consumption is after market on
that step. Private rival inventory and hidden RNG are not runtime inputs.

Synthetic small fixtures establish local semantics. The no-rival/rival values are
separate conditional scenarios, not estimated probabilities. An artificial short
planning horizon must retain a continuation value for unsold stock; zero salvage
applies at the actual match end. This report does not infer a full-game win from
the $52 small-case gain.

Source receipts:

- Official engine commit: `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
- `kaggriculture.py` SHA256: `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.
- `kaggriculture.json` SHA256: `a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867`.
- Global `kaggle_environments/utils.py` SHA256: `537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b`.
- Existing `reference/evaluator/evaluate.py` SHA256: `e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c`.
- Tested `mechanics.py` SHA256: `579965e589237d1e5bbcc8b8448188f91b173d4480430d34b3a7f0e07e0c48d3`.
- `test_engine_semantics.py` SHA256: `fc0a65f98fc78e4dc0cc5e1b553a53d514276fe83fb3106d4ed55f028b0305f6`.
- Complete terminal-window game trace SHA256: `a1c572f063bf9ea2fe5b937c2c6218f815a2b3ee45a6c0fa5ea8708df5947cfc`.

The complete terminal-window probe's maximum measured policy call was
0.000053042 seconds. This probes the tiny window policy only; candidate runtime
and cold-start allowance must come from its separate full-game benchmark.
Official Apache-2.0 attribution is preserved under `reference/engine/LICENSE`;
the existing evaluator's retained license files remain under `reference/evaluator/`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
