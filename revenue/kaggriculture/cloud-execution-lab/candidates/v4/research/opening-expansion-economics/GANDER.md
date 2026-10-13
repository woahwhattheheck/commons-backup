# ASTRA-GANDER — source-bound Goose Printer opening oracle

Research-only evidence for the single TITAN V4 line. This package consumes the fresh “Goose Printer” build demand without promoting its literal opener.

## Result

The **mechanism is real but the proposed opener is not**.

Pinned official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`.

For a surviving placed animal, `_daily_refresh_animals()` sets `fertilizer_available=True` after the first-yield gate, so a Day-0 goose can expose fertilizer at EOD0 even though its first EGG yield is Day 4.

But the literal “buy 10 geese, then 10 BUILD_COOP + 10 PLACE actions” story omits engine requirements:

- market processing occurs **after** unit actions, so Day-0 purchased geese cannot be picked up until the next callback;
- `BUY_ANIMAL` lands geese in the shed;
- animal `PLACE` consumes a goose from farmer/hand inventory while standing on an already-built matching structure;
- ten distinct coops require movement between sites.

With $3,000 starting cash, ten geese consume the entire bank, so even the first $1 HIRE is unaffordable. One worker then has only steps 1..23 before EOD0, while the exact lower bound is 1 PICKUP + 20 BUILD/PLACE + 9 moves = **30 unit actions**. Therefore 10 is impossible.

The largest constructively certified Day-0 frontier is **9 geese + one $1 HIRE**. Both workers pick up after the step-0 market fill, use disjoint NW routes, and all nine geese are placed by step 15. EOD0 leaves $299 cash, zero eggs, and nine fertilizer-ready animals.

## First keep-alive cycle

The oracle also constructs a Day-1 two-worker service route. A $1 HIRE and nine WHEAT buys cost $247 total ($1 + $246). Both workers FEED and COLLECT all nine geese and return fertilizer to the shed by step 45, where the same callback’s market stage can sell all nine units.

Exact reduced market prices from the pinned formula:

- nine WHEAT: `26,27,27,27,27,28,28,28,28` = **$246**
- nine FERTILIZER: `100,100,100,99,99,99,99,99,98` = **$893 gross**

Closing liquid cash after that keep-alive cycle is **$945**, versus $3,000 for simply holding cash. This is not a Day-1 capitalization printer. It may still have longer-horizon value through later EGG production, fertilizer, opponent/market effects, or composition with other opening logic; this package makes **no promotion/strength conclusion**.

## Source contract

`goose_printer_oracle.py` fail-closes unless the official engine bytes have Git blob `3c202c7e...`. It then source-checks GOOSE metadata, the direct post-survival fertilizer assignment, unit-before-market chronology, and the standard starting-money / market-order / turns-per-day defaults before emitting a report.

The package constructs the Day-0 `0..10` frontier rather than equating “mechanism true” with “10 is optimal”; it also constructs the 9-goose Day-1 FEED/COLLECT/DROP route and mirrors only the pinned WHEAT/FERT market formulas needed for the cash ledger.

Branch source Git blob: `38ae7715c233c74f24aacd5fe09f4d0d7a630037`.
Branch test Git blob: `59e33b44979d7f05849fe4dc6ca29ac9d992269e`.

## Authoring receipt

The source-independent contracts were executed locally in normal and optimized Python: 10 PASS plus one expected SKIP for the exact repository-byte binding because the authoring container did not have a repository checkout. `py_compile` passed. The canonical engine was independently read through GitHub during authoring and matched the pinned blob above.

The full-checkout test is designed to stop skipping in repository CI/review environments and authenticate the engine bytes before the source theorem is accepted.

## Integration boundary

This is deliberately **not** a second controller. It does not touch runtime/default/config/archive/evaluator/Kaggle state. The next gameplay gate should consume this certified frontier rather than the falsified 10-goose premise, compare smaller goose counts and current opening policy under both seats / real opponents, and keep the mechanism OFF unless those economics clear.

No historical V3/V3.1 goose carrier is relabeled as this V4 result.