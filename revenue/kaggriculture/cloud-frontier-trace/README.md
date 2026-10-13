# Public frontier trace

Public episode106392861 is downloaded and analyzed: all719 transitions reconcile; terminal139044/106987 is confirmed. See OBSERVATIONS.md and results/106392861/. Reusable fetcher, analyzer and timing contracts are implemented; six focused tests pass. No candidate-improvement claim is made.

From repository root:

```sh
python revenue/kaggriculture/cloud-frontier-trace/fetch_public.py 106392861 --output replays
# When ordinary official CLI is already configured:
python revenue/kaggriculture/cloud-frontier-trace/fetch_public.py 106392861 --output replays --configured-cli
python revenue/kaggriculture/cloud-frontier-trace/analyze.py replays/episode-106392861.raw --engine-dir engine-cache --output trace.json
KAG_ENGINE_DIR=engine-cache python -m unittest discover -s revenue/kaggriculture/cloud-frontier-trace -p test_trace.py -v
```

Reuse cloud-eval's pinned official engine preparation and source/license verification. No competitor code is loaded. The raw replay is parsed as JSON, gzip or a single-member ZIP, with explicit recognized envelopes. Actions in frame i consume observations in frame i-1. Requested actions, observed money and prices, and reproduced effects remain separate. Only economic transitions matching the next recorded state contribute executed totals. Boundary weed positions and new shop draws are explicitly excluded. Private inventories must be present for effect reconciliation; missing observations remain unavailable. Unchanged actions do not prove avoidable worker waste.

Tests use targeted manufactured recorded-action fixtures, including a day boundary, a corrupted balance and omitted private inventory; these are not public leader results. Initial two tests passed in the cloud runtime. Earlier dispatch studies were not rerun.

Source basis: Google/Kaggle kaggle-environments, Apache-2.0, commit 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c. Transport basis: Kaggle/kagglesdk commit f983c97287bf274ebab506aac85eda6efebe3b32. Keep upstream notices with the existing engine cache; this package does not redistribute upstream engine files. Modern public POST returned HTTP 401 before a configured credential was available. Root's UI-reported terminal money 139044 versus 106987 remains unverified against replay bytes at this checkpoint.

Assigned additive interface: production-event timing and harvest deadlines. FLORA owns scheduling policy, SORREL owns persistent plan context, root owns Claude decisions and submissions. Event helper and actual replay results follow this source checkpoint.

## Timing contract (implemented)

`events.py` is stdlib-only and importable independently of the analyzer:

- `production_events(tile, step, turns_per_day=24, episode_steps=720)` returns conditional EOD refresh/availability steps, held capacity and fertilizer/care conditions for installed ongoing crops and animals.
- `harvest_contract(tile, step, ...)` adds maturity, first-decay/capacity-relief deadlines and immediate survival need.
- `liquidation_window(step, harvest_travel_steps, return_travel_steps, *, turns_per_day=24, episode_steps=720, depot_has_capacity=True)` uses caller-provided legal travel costs. HARVEST and DROP consume separate actions. Same-action DROP precedes market; automatic EOD deposit follows market and can sell only next action. Capacity must be reserved by the caller.
- `farm_contract(observation, configuration)` exports coordinate-tagged held-yield contracts for FLORA/SORREL.

Concrete source-derived implications: a day-zero strawberry has four base production opportunities available on days 10,12,14,16, not indefinitely. To double the first event, water on day9 and apply fertilizer during days7–9 (inclusive). Held capacity can erase the bonus without intervening harvesting. Day20 strawberries first yield on day30, beyond this 720-frame episode's last action718. These are interpreter rules, not claims about the leader's choices. Future survival and output remain conditional; future prices and net returns are deliberately not guessed.

Five distinct focused tests now pass: actual interpreter strawberry refresh agreement; terminal/decay/maturity timing; held capacity and animal-care semantics; recorded buy/sell/hire transitions with zero cash residual and corrupted-state detection; missing private inventory. No candidate game or leader replay result is implied. Rule tables derive from the pinned upstream source; no upstream license terms are changed.

`fertilizer_contract(tile, step, ...)` selects the next uncovered realizable ongoing-crop event using the correct refresh day. `summarize.py TRACE --output DIR` generates a compact economic summary, daily cash, exact per-unit cash ledger and compressed full trace. Historical checkpoint notes above retain their original pending status; the current completed replay result supersedes those statuses.

## Raw-verified decision moments

See DECISION_CONDITIONS.md for the actual shop/price/allocation sequence, labor spending versus changed/nonmovement action throughput, tomato/cow cadence and complementary same-tile assignments. Reproduce the detailed context extraction with:

```sh
python revenue/kaggriculture/cloud-frontier-trace/moments.py replays/episode-106392861.raw replays/analysis.json --engine-dir engine-cache --output moments.json
```

`results/106392861/decision-cases.json.gz` preserves20 exact original before/after frame pairs for offline candidate regression inputs. `moments.json.gz` contains all instrumented context; `decision-summary.json` retains shop, labor and joint-operation tables. `decision-manifest.json` binds these follow-up files to the unchanged original replay hash. These are observed witnesses and decision conditions to test, not a promoted policy.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
