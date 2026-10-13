# TITAN V4 COMEBACK — authenticated counter-ambush market economics

**Disposition:** research-only, default-neutral, no decision authority.

This is the canonical COMEBACK interpretation layer for the Gemini/Antigravity Apex counter-ambush seam. It now consumes the separately landed source-custody proof instead of treating the Apex schedule as external metadata. The exact public Apex V7 wrapper is bound at SHA256 `1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a`, matching the canonical reference-policy bank. No second seller/controller is created.

Authenticated Apex anti-clone events: MELON 249 up to 12; STRAWBERRY 381 up to 8, 403 up to 8, and 499–501 up to 8 each; FERTILIZER 522 up to **4** via `min(fert - 16, 4)` when the clone/stock guards fire.

## Official-engine boundary

Pinned engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

The oracle mirrors only mechanics needed by these counterfactuals: per-unit market pricing, the $1 SELL supply-floor exception, BUY_PRODUCT post-buy quoting/inventory decrement, fertilizer production ceiling, and callback ordering UNIT -> MARKET -> TOWN. `verify_engine()` fail-closes on exact engine bytes/source anchors. `verify_apex_source()` separately fail-closes on both the exact Apex wrapper SHA256 and the reference-policy-bank declaration.

## Strawberry pre-dump — source-real quantity

The t-1 idea is mechanically real but shop timing matters. Step 380 is divisible by four, so already-unlocked Strawberry-consuming shops drain stock after our market stage and before Apex step 381. The source-real Apex block is at most 8 units, not the old synthetic 10.

At market inventory 10,000 with our sale 8 and Apex sale 8:

- step 380 with eight Strawberry-consuming shop instances: town drain 8, own early-vs-late gain $0, Apex suppression $193, gross relative-margin swing $193.
- step 402 with no shop drain before Apex 403: own timing gain $121, Apex suppression $121, gross relative-margin swing $242.

So the useful descendant is **public-state-conditioned sale timing**, not a blind static `380`/`402` trigger. Current market inventory, unlocked-shop multiset, authored stock, row displacement, rebound, and both-seat terminal margin still gate any promotion.

## Fertilizer sponge — authenticated falsification

The older COMEBACK sensitivity example used a synthetic 40-unit dump. That was useful as a market-function stress test, but it is **not Apex-real**. Authenticated Apex sells at most 4 FERTILIZER at step 522.

At market inventory 10,000, exact max-four Apex sell followed by our buy of four:

- buy cost after Apex: $399
- buy cost without Apex: $402
- direct opponent-created quote discount: **$3**
- source-max WHEAT bonus: 2 extra units per fertilizer
- four FERT at base WHEAT $25 has optimistic crop-value ceiling $200 vs $399 fertilizer cost
- gross WHEAT sale-price threshold to cover fertilizer alone: $50/unit

At FERT inventory 10,493, the $1 SELL floor adds **zero** market units; the four-unit Apex event creates **$0** direct buy subsidy. Therefore the Gemini “fertilizer sponge” is falsified as a large Apex-specific subsidy. Do not field it as an opponent response. The old 40-unit scenario is retained only in git history as synthetic sensitivity, not current Apex evidence.

BUY_PRODUCT still lands fertilizer during MARKET after UNIT; best-case BUY523 -> PICKUP524 -> FERTILIZE525 before movement delay. That timing alone does not rescue the economics.

## Validation

Fresh source-convergence authoring:
- `python -B test_counter_ambush.py`: 15/15 PASS
- `python -O -B test_counter_ambush.py`: 15/15 PASS
- `py_compile`: PASS

This convergence packet does not claim current-native games, hosted-CI green, runtime activation, config/default/archive/workflow/evaluator/Kaggle/submission mutation, or positive economics.

## Handoff

SELLWINDOW / CRASH / TOWNCLOCK and the existing rival-route-pressure / D4 timing evidence retain sale-timing ownership. FERTWARE / FERTDEADLINE / HERDSCALE retain fertilizer runtime/service policy. ORDERBUDGET retains market-row capacity. The separately landed `research/market-pressure` Apex packet remains the source-custody/evidence witness; this COMEBACK package is the canonical interpretation, now corrected to consume that authenticated source rather than contradict it.
