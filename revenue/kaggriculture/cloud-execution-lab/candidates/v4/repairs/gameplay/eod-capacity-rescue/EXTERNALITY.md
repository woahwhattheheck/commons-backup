# EOD rescue: rival externality and a public floor envelope

This extends the **existing EOD rescue family**, not a second controller. It adds a usable source-pinned paired interpreter runner and a callable `floor_envelope` verifier. No production runtime, existing helper, feature key, default, archive, or submission is changed.

## The concrete economic failure

At step 119, give our farmer 8 carried FERTILIZER with a shed already containing 100. Public fertilizer inventory is 10,493 and the observed price is $1. Both farmers PASS, the rival starts with an empty shed, both have $1,000,000 to remove affordability confounding, and the rival submits `BUY_PRODUCT FERTILIZER 100`. The exact current whole-vector helper appends `SELL FERTILIZER 8`.

The full official unit/market/town/EOD transition gives **our cash +15, rival cash +131, margin -116**, identically in both seats. Both complete private states are equal between ON and OFF after EOD; the public market is not equal. Rival purchases lift the price during the per-unit lockstep row, so later rescue sales add supply and subsidize the remaining purchases. An observed $1 quote is not sufficient evidence that an entire sale is supply-neutral.

These are deliberately constructed states, not evidence of natural encounter frequency, reachability from a sampled match, expected value, or whole-game performance.

## A positive boundary, not only a veto

For a validated rescue SELL of quantity `q` at zero-based **raw** market slot `j`, with standard shed capacity 100:

- For WHEAT and FERTILIZER, bound rival withdrawals before its last quote by `100*j + q - 1`.
- Other products cannot be purchased with `BUY_PRODUCT`; their withdrawal bound is zero.
- Evaluate the actual pinned pricing function at **every integer inventory** from the observed level down through that bound, using the observed public pricing parameters. Certify only when every quote is exactly $1 for every appended product.

Why the bound works: a rival purchase row can fill at most 100 shed places, regardless of its requested quantity; earlier sales may free room but occupy separate raw slots. During the concurrent row only one rival unit can commit between consecutive own quotes. Under the floor certificate, neither player's SELL at any reachable pre-quote inventory increases public supply, so inventory cannot escape above the observed level. This induction also explains why no monotonic-price assumption is needed. Purchases may move below the certified interval after our final quote, but our already-completed sales have then caused no public-state change.

The unchanged parent prefix and units execute identically. Certified added sales change only our cash; rival quotes, affordability, orders, and public state remain identical. Compose this with the existing helper's private-shed conservation proof. **The verifier does not establish that private proof, or replace the helper's action/configuration guards.** A negative certificate means unproved, not necessarily a bad trade.

A useful sharp example is slot 0 with 8 fertilizer: public inventory 10,500 is certified, while 10,499 is not. Selling a single fertilizer at slot 0 is certified even at inventory 10,493: the sale is quoted before the rival's first withdrawal. Empty parent rows still consume raw slots and cannot be filtered out.

## Execution receipt

`EXTERNALITY-RECEIPT.json` records 16/16 normal and 16/16 optimized tests, six deliberately broken certificate implementations rejected in each mode, and identical normal/optimized full matrix bytes. Each standalone matrix contains 1,080 ON/OFF pairs (3,240 full interpreter calls including initialization), 80 negative-margin cases, 460 certified cases with zero certificate false positives, and a worst constructed margin delta of -314. Invalid BUY_PRODUCT MILK/STRAWBERRY rows are explicit nonexecuting controls, not rival-purchase engagement.

The real interpreter, complete EOD helper, complete H3c dependency, and actual upstream seed-helper AST execute. The `r04_full_router` binding supplies **only official PRODUCTS constants**; no whole-router or native-agent integration is claimed. Exact five-file source pins are checked before execution. Changed or missing source exits unsuccessfully without replacing an earlier report.

## Reproduce without new compute dispatch

Use the existing artifact 10123395668 from run 34400824037 for its `final-pressure-runtime/checks/reference/engine` directory. Use the current canonical `candidates/v4/donor/overlay` directory for the two helper files. The historical `2c031fce` helper in this repair directory is provenance, not the `9ad40924` helper under test; passing that older packet as the overlay intentionally fails the source pin.

From this repair directory:

```sh
export TITAN_ENGINE_DIR=/path/to/final-pressure-runtime/checks/reference/engine
export TITAN_V4_OVERLAY=/path/to/candidates/v4/donor/overlay
python -B -m unittest -v test_eod_market_externality
python -B -O -m unittest -v test_eod_market_externality
python -B eod_market_externality.py --engine-dir "$TITAN_ENGINE_DIR" --overlay-dir "$TITAN_V4_OVERLAY" --output matrix-normal.json
python -B -O eod_market_externality.py --engine-dir "$TITAN_ENGINE_DIR" --overlay-dir "$TITAN_V4_OVERLAY" --output matrix-optimized.json
cmp matrix-normal.json matrix-optimized.json
```

The main EOD integrator retains the current-ABI/final-return seam. This packet supplies a concrete adverse regression plus a sufficient public-only no-subsidy envelope to consume there. Actual runtime composition, natural engagement, and paired full-game economics remain distinct work, not inferred from this matrix.
