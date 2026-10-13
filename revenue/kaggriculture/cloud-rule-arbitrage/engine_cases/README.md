# T11 economic-cycle component

Runnable research over the frozen SELL default. The guarded cycle adds one own
cash in six paired games across 36 development and 24 held games, with rival
cash unchanged and no outcome flips. Keep selected SELL
as the production default; use this source and its exact quotes for subsequent
flow-conditioned experiments. This is legal observable game play, with no
Kaggle writes, external trades, paid services or owner-PC execution.

## Callable

```python
from liquidity_cycle import LiquidityCycle
economic = LiquidityCycle()
# The caller owns and invokes its production controller once.
action = economic.transform(obs, cfg, supplied_base_action,
    reservations={"stock": {"WHEAT": 6}, "market_slots": []})
```

It copies the base action, preserves all unit actions, and uses only an empty
market queue. Any reserved market slot prevents a cycle. Reserved operating
stock and all requested same-action pickups are excluded. The standard-price
candidate sells one observed WHEAT or FERTILIZER and rebuys one in slot1 only
when rival visible cash cannot fund a slot0 purchase, the marginal buy/sell
quote is flat, and the possible slot0 supply stays above the sale-admission
floor. It does not instantiate or invoke a production controller. No future
opponent orders, private opponent state, evaluator seed, probabilities or
history prediction enter it. require_flat=False is a preserved experimental
option with a demonstrated rival-discount counterexample; main.py uses True.

`main.py::agent(obs, cfg=None)` invokes frozen SELL exactly once then applies
the transform. The relocatable `artifacts/t11-liquidity-research.tar.gz` uses
the official-loader-compatible raw_main.py entrypoint, which delegates to that
unchanged policy saved as t11_policy.py. It retains every selected vendor byte
and license. The lazy adapter uses the pinned loader's __raw_path__ to locate
the policy module; it adds no policy/controller state.
It is a research artifact, not a promoted or uploaded submission.

`cycle_quotes.sell_rebuy_quote(item, I, q, r, rival_direction="SELL")` exposes
conditional integer-unit receipts and both players' cash/margin differences.
Its scenario quantities are caller hypotheses, not forecasts. probability is
always None. The function requires full fills, non-floor sales and no later
rival same-product orders; outside those conditions use official transitions.
See ALGEBRA.md and results/engine.json.gz for exact positive and contrary cases.

## Evidence and reproduction

11 test groups, 158 saved engine cases, 60 scored full games. Each game executes
719 decisions, final action718. Development9832001/9832019/9832037; held9832101/
9832119. Both seats versus unchanged Arlene/Apex and frozen SELL, with a paired
frozen-SELL control. Own cash increases by exactly1 against Apex on development
9832019/9832037 and held9832119, both seats. Rival cash is unchanged in all30
pairs; the remaining24 own-cash deltas are zero. Candidate WTL: dev12/6/0,
held8/4/0; the same as control. No leaderboard claim.

Retained held9832119/Apex/seat0 action101 captures a paying case: WHEAT stock
9969, rival cash4, our SELL1/BUY1 and rival SELL2. Own cash67 becomes68; rival
cash4 becomes65. The exact conditional quote gives own+1/rival0 against the
no-cycle comparison. Rival SELL2 is evaluator evidence, never a runtime input.

The runtime was this Work cloud VM: 8-CPU quota, 20 GiB memory limit, Python
3.12.13. Candidate maximum action229.114ms; maximum held210.190ms; cold first
action29.420ms. Maximum candidate full-episode wall time8.057s. The evaluator
enforces a 1s action RPC and 120s episode wall allowance with zero overage;
these are measured offline limits, not a claim about hosted infrastructure.

The evaluator converts dynamic Struct subclasses to plain JSON for process-pool
results. `results/development/transport-error.log` and the corresponding manifest
preserve the initial collection attempt; no score was read from that attempt.
The development recovery preserved policy bytes. SOURCE-FREEZE.json
was written before held and every frozen file remains unchanged.

The event logger records exact two-order cycle signatures, including some
incumbent SELL actions. These counts alone are not attributed override counts.
RESULTS.json keeps both receipt series and paired deltas. Compressed raw
reports retain all observations/actions recorded by the passive event logger.

```sh
T11_ENGINE_DIR=/path/to/engine python -m unittest discover -s . -v
python official_cases.py --engine-dir /path/to/engine --output new-cases.json
python panel.py --engine-dir /path/to/engine --runtime /path/to/opponent-runtime \
  --seeds NEW_UNUSED_SEEDS --output new-panel --workers 3
python analyze.py
python build.py
python verify_raw.py
```

Use existing cloud-frontier-policy/next-panel/prepare.py to prepare the offline
Arlene/Apex runtime, and the pinned three engine source files. No new source
export job or dependency installation is required. Existing scored panels are
preserved; new experiments need new seeds and an explicit source freeze.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
