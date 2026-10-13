# Terminal feed-stock admission: HERON

Status: inactive native-consumer admission experiment, built and engine-tested in the sole `main:candidates/v4` workspace. This is not a production enablement, a new controller/key, a whole-agent game result, or a Kaggle submission.

## Executed finding

The current native `operating_stock.py` blob `781aa90da0d85d0ba23c665e29d6087d182c085e` can certify a physically reachable feed that has no remaining survival or care-production payoff. Concrete initialized fixture: step 690; two shed WHEAT; authored SELL WHEAT 2; hand PICKUP at 691, FEED at 693 and 695; existing unstarved animals with zero pending/current care. Current guard suppresses the sale. The exact official interpreter through DONE at step 718 returns $50,000 with the reservation versus $50,049 with the original sale, with identical animal survival, held product and private cargo. Animal starvation counters and the global WHEAT market differ; they are not claimed equivalent inputs to a future adaptive policy.

The last full-day refresh executes at step 695. Base animal output does not require feeding; a first missed feed does not cause escape. There is no later full-day refresh before DONE 718. These facts do NOT justify skipping escape-preventing feed or feed that realizes pending care bonus. Executed negative controls show an animal escaping when a second missed feed is allowed, and a due COW producing 1 instead of 3 units when pending-care feed is removed. Applying the rule one day earlier also causes an escape at the subsequent refresh.

## Candidate contract

`terminal_feed_gate.py::admit_terminal_feed_override` is an admission filter after the EXISTING native `protect_feed_stock` result, not a replacement reachability planner. It only restores the exact pre-feed-guard selected object when every protected target has a complete record with zero prior unfed days, zero pending care, no current care, and no future CARE anywhere in the remaining full day. It requires standard configuration, two physical seats, a changed/certified native report, steps 672..694, and window end 695. Mixed useful/useless obligations are left unchanged. Unknown, malformed, unsupported and nonmatching inputs preserve the exact delegate action/report objects. No partial feed redistribution is attempted.

The proposal must differ solely by shrinking executable-prefix WHEAT SELL rows. Unit edits, different products, metadata edits, row additions/removals and raw-suffix edits block restoration. Other stages' work must not be undone. This helper is deliberately not imported by production and creates no feature flag. It neither touches the active FERT-prefix work in the same production module nor calls the legacy r04 materializer.

## Validation executed

13/13 tests normal and 13/13 optimized. Each full run executes 864 initialized fixed-route terminal pairs and 50,556 official-interpreter calls, including the negative controls. Matrix: both seats, COW/SHEEP/GOOSE, six placement phases, two held-yield levels, farmer/hand service, three initial WHEAT market inventories and one/two retained units. Original-sale terminal cash advantage is $19..$90 in that matrix. The opponent is passive, and the suffix is fixed. These are mechanical counterexamples, NOT 864 natural games or a measured field-strength gain.

All six deliberately broken variants are rejected by assertions in both modes: ignore starvation, ignore pending care, ignore future CARE, ignore proposal custody, admit the penultimate day, and never release the reserve. All 24 existing native feed tests also pass in normal and optimized modes. The named input hashes are rechecked after execution; a missing runtime exits 2 before imports.

## Reproduce without new compute jobs

Use an existing extracted runtime containing the exact inputs named in `PINS.json`. The executed source copies came from existing GitHub artifact 10123395668, directory `final-pressure-runtime`. This artifact authenticates the named component inputs, NOT the freshness of the complete current production archive. No workflow was dispatched.

```
python check_terminal_feed.py --runtime /absolute/path/final-pressure-runtime --receipt NORMAL.json
python -O check_terminal_feed.py --runtime /absolute/path/final-pressure-runtime --receipt OPTIMIZED.json
python check_terminal_feed.py --runtime /absolute/path/final-pressure-runtime --smoke --mutant ignore-starvation
```

The mutant command must fail with test assertions and exit 1; an input error/exit 2 is not a mutation kill. Available mutation names are enumerated by `--help`. Existing feed-suite command: `PYTHONPATH=RUNTIME python -m unittest discover -s RUNTIME/checks -p test_feed_stock.py -v`, repeated with `python -O`.

## One remaining evaluation lane

Use the existing exact-current-package evaluator to count NATURAL terminal `feed_stock.changed` reports and matching gate inputs first. Record parent/runtime/helper hashes, seed, seat, step, original and proposed final market prefixes, completed post-unit animal facts, route identity and skip reason. A zero-match panel parks this gate without broadening its conditions. Positive matches authorize an experimental, explicitly opt-in evaluation at the current `_feed_stock_selected` seam immediately after its delegate and before downstream owners, followed by matched whole-agent both-seat/opponent-diverse economics. Bind the same completed unit snapshot and route; do not post-wrap a later returned action. Log final own/rival cash, feed/care/escape events, retained units and subsequent stock/market/policy effects. No activation follows from this README alone.

Canonical source commits before bundle completion: gate `62741c6acd5bc75e8672745fba058e072533bd03`, pins `536cf652fc98b67c0182ccc3a2a6165680113656`. A test Contents write lost a main-ref race but preserved the exact tested Git blob; this bundle adds that same object rather than rebuilding it. Author/claim: ASTRA-HERON, #titan thread 1789180189.887299.
