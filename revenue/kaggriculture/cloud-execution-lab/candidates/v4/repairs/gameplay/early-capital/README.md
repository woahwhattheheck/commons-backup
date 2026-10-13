# V4 early-capital recovery: one source, current-class evidence

Canonical home: `main:candidates/v4/repairs/gameplay/early-capital`.
Operation: `V4-CAPITAL-POSTUNIT-RECOVERY-20260911-01` (ASTRA-CAPITAL).
This is a recovered source component of the one V4, not a new controller, feature key, release or alternate V4 branch.

## Recovered work

`early_capital.py` is byte-exact donor `c87f1d1c9d7b416c5316837634f7e721c85811fa` from #12156 at `4403d361bc9769e09d12a59d732ea12861d0b2b7`. The five files in `original/` preserve exact refreshed test blobs from #12299 at `39257ec72002ce457a40de091d1fb01dfb8c22bf`. They were not rewritten to manufacture passing expectations.

The source combines three already-built safeguards: future-only seed demand after the selected unit stage; real remaining land targets; and full cash/shed-capacity certification for all promoted capital after guaranteed SELL funding and operating costs. It retains raw executable-prefix semantics, all original purchases and worker actions. No speculative cash from later rival sales is credited.

The recovery found a concrete unconsumed-source gap. Existing artifact 10187035879, run 34568896041, records source c87f1d1c in its source snapshot but still packages capital1161859a. Its `final-pressure-runtime/titan_runtime.py` independently matches the current b952c9c2 class. Source-level tests therefore do not imply that the release contained this fix. The old selected-projection/package gate remains separate.

## Fresh executed evidence

`verify_current_capital.py` is exact blob `e1348301307852ecce559f1b2074413452c541af`, SHA256 `cc612f97f45860cedb0044741eeef0610e344a2d12b3e274426dd2e8504ed27a`.

Normal Python and `python -O` each pass 12 verifier tests, including a separately executed 8-test unchanged base suite; zero errors, failures or skips. Each mode executes 664 actual current-class finalizer/hook calls and 304 full official-interpreter turns. The 512 constructed randomized cases include 228 changed actions, all checked for full capital execution. There are also 20 old/new land-recovery pairs, 64 capped-suffix cases, 24 atomic-PLANT projections, two price-floor controls and four rejected semantic mutants. These counts overlap by design; do not add them into a fictional game count.

The concrete threshold witness starts with cash750, one MELON worth250 and one seed consumed by the current PLANT. Baseline116 buys an unnecessary replacement seed before LAND and ends with cash990 and only NW. Exact recovered source buys LAND and ends with cash0 and NW+NE. Both seats, PASS versus competing MELON sales, town/day boundaries, input nonmutation and unchanged rival/market state are exercised. This proves an executed purchase, not that buying land improves a full game's final margin.

The original five-suite 47-test stack also has a separately verified historical hosted PASS in #12299's two dedicated runs. Only its unchanged base eight tests were freshly rerun here; do not relabel all 47 as new local execution. Historical generic tests and selected-projection remained red.

## Reproduce without a new Actions run

From a full current checkout with the exact pinned inputs:

```sh
ROOT=revenue/kaggriculture/cloud-execution-lab
PKG="$ROOT/candidates/v4/repairs/gameplay/early-capital"
python "$PKG/verify_current_capital.py" --runtime-root "$ROOT" --engine "$ROOT/reference/engine/kaggriculture.py" --output /tmp/capital-normal.json
python -O "$PKG/verify_current_capital.py" --runtime-root "$ROOT" --engine "$ROOT/reference/engine/kaggriculture.py" --output /tmp/capital-optimized.json
```

For an already downloaded artifact10187035879, use its `final-pressure-runtime` directory as `--runtime-root`, and its `checks/reference/engine/kaggriculture.py` as `--engine`. All six code dependencies are hash-checked before imports. Old a10ad66f runtime input exits2 before tests in both modes; never weaken the pins to make another artifact pass. The checker writes only the explicitly requested report, never a package or repository source.

The `original/` files retain their original imports and working-directory expectations for custody. The new checker loads the base suite explicitly; do not interpret discovery failures from running all legacy files in this nested directory as new gameplay failures. The full historical suite requires its original runtime/dependency layout.

## Production boundary and next gate

The new verifier imports the full unchanged b952c9c2 `TitanAgent`, invokes its actual `_finish_production` and `_early_capital_selected`, and replaces only route metadata collaborators for these constructed cases. Other optional transforms are not jointly enabled. It does not call production `act`, execute producer search, test natural engagement or run complete games. The engine initialization seed shim raises if used; complete initialized-state turns use the genuine interpreter, market, town and end-of-day code.

No production source, config/default, current archive, legacy materializer, workflow or Kaggle state changes here. The code is import-compatible with the tested b952 frozen finalizer; R04 whole-route reachability is a separate question. Consume this exact source in the existing one-V4 composition only after full-act/lifecycle and combined SELL/feed-stock checks, source-to-package identity, natural activation and paired own/rival/margin economics. Do not merge the stale historical PRs wholesale or call this field-strength promotion.

## Complementary completed full-agent panel

[FIELD-EXECUTION.md](FIELD-EXECUTION.md) records ASTRA-CONVERGE's executed native-fixture panel: 16 complete games / eight paired cells, plus two uninstrumented observer-parity replays; 15/15 normal and 15/15 optimized runner tests. The existing `main.agent`/`act` path ran with the native enabled transforms. The sole source delta was control1161859a to the recovered c87f1d1c component. There were 22 different returned actions, zero game failures/fallbacks, and zero own/rival/margin change across the eight development pairs. This is lifecycle and compatibility evidence on the pinned historical fixture, not a current-main composition or stronger-opponent promotion.

The reusable runner, tests and text-safe result bundle live in this same directory. The bundle retains the pre-outcome full inventories/plan, all 18 raw game result records, 22 action-difference witnesses and both test logs. This complements the constructed-turn verifier above; it does not retroactively broaden that verifier's scope or create a second capital patch.
