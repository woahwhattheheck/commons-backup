# Effective opponent-flow bounds — ESTUARY-0891

## Status and ownership

Built and executed as an additive support component in the existing canonical
`main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/lockstep-scale`.
This is not another observer, SELL producer, controller, V4 root, or default flag.
LOCKSMITH retains native returned-action/ledger integration. FLOWPROOF provides
independent oracle validation; CROSSCURRENT and ESTUARY-ROW own complementary
queue/collateral and timing-economics evidence. Their results are not implied by
this component's green tests. Original lockstep-scale evidence is unchanged.

## Executed defect

At step 101, own cash is zero, own returned market action is
`BUY_PRODUCT WHEAT 1000`, and the rival passes. The complete pinned official
interpreter executes in both seats: our buy fills zero, the rival adds zero
inventory, and the previous/current wheat inventory is unchanged. Nevertheless
the handoff's displayed `delta_inventory - requested_own_net + town` expression
reports an opponent dump of **1,000 wheat**, above its advertised threshold 150.
This is not merely small partial-fill noise.

The new helper returns wheat bounds `(0, 1000)` and no confirmed positive signal.
The original inline donor was not byte-authenticated or executed: the comparison
is explicitly to its displayed formula, not a claimed run of the whole donor.
The early town-clipping hypothesis was rejected: engine town consumption is NOT
clipped at zero. Negative inventory and duplicate shop instances are tested.

## Mathematical contract

For product p, let `R = I_next - I_prev + C_prev`, where C is exact deterministic
town consumption under the previous snapshot's shops and the actual configuration.
Let S and B be sums of executable own SELL and BUY_PRODUCT requested quantities,
respecting the raw market-row prefix and the official per-row 99,999-unit limit.
Only WHEAT and FERTILIZER are valid BUY_PRODUCT items. Invalid/empty rows consume
slots; they must not be filtered before applying the row cap.

Our inventory-changing contribution A satisfies `-B <= A <= S`, irrespective of
cash, stock, partial fills, simultaneous opponent trades, or invisible $1 sales.
The opponent contribution is `R - A`, hence it lies in `[R-S, R+B]`. This envelope
can be loose; widening uncertainty is intentional, not a failure to fill it with
requested orders. With no own product rows, the interval collapses to R exactly.

These bounds describe **effective net inventory flow**, not total opponent sales,
unobserved floor sales, or a prediction of the next callback's action. Only a
sufficiently positive LOWER bound can certify net inventory-increasing sales.
Even a correct retrospective signal is not a positive-EV join certificate.

## API and integration requirements

```python
from effective_flow_bounds import effective_flow_bounds, confirmed_net_sells
bounds = effective_flow_bounds(previous_obs, exact_returned_action, next_obs, cfg)
certified = confirmed_net_sells(bounds, threshold=150)
```

The helper reads public `step`, `player`, `market.inventory`, and the previous
`town.unlocked_shops`. No opponent action or private state enters inference.
It is stateless, input-preserving, and dependency-free. It returns all nine
product intervals or `None` for missing/invalid/nonadjacent evidence; the signal
helper maps inconclusive evidence to `{}`. Missing input is not zero flow.

The caller must bind the exact final returned action, actual configuration,
successfully completed transition, same seat, and same episode. Adjacent numbers
alone cannot prove episode identity. Preserve previous shops across an EOD shop
unlock. Reset/invalidate accumulators on gaps, cancellation, or episode changes;
do not turn an unknown interval into zero. Summing valid adjacent intervals is
conservative, but lifecycle/day assignment is the observer owner's responsibility.
No runtime hook, route mutation, configuration edit, or native activation is
included here. Native consumer planned lots and economic admission remain with
their existing owners, not this public-data helper.

## Reproduction

From the repository root, with the pinned reference files already present:

```bash
LAB=revenue/kaggriculture/cloud-execution-lab
LANE="$LAB/candidates/v4/research/lockstep-scale"
python "$LANE/test_effective_flow_bounds.py" --reference-root "$LAB/checks/reference" -v
python -O "$LANE/test_effective_flow_bounds.py" --reference-root "$LAB/checks/reference" -v
python "$LANE/run_effective_flow_controls.py" --reference-root "$LAB/checks/reference" --out /tmp/estuary-flow-controls
```

The suite authenticates all four reference files before importing the existing
loader: full engine, specification, upstream seed utility, and loader. Missing
or changed bytes fail, with no network download or skip fallback. The existing
loader compiles the actual upstream seed helper and loads the entire engine.
Tests call the full interpreter. A test-only pass-through wrapper records each
seat's inventory deltas while calling original `_commit_unit` unchanged; hidden
oracle truth is never supplied to inference. This is not a full-game driver.

Executed results in **each** normal and optimized mode: 17/17 tests, 463 complete
transitions plus 465 initialization calls, 400 randomized worlds, 4,167 product
containment checks, zero failures/errors/skips. All 12 semantic mutants reach the
real suite and fail assertions. All eight missing/modified reference controls
fail before testing. The quantity-limit test checks the bound using early-exit
orders; it does not force 99,999 successful purchases. First floor fixture used
too little wheat inventory to reach $1; its price assertion rejected it. The
corrected executed fixture independently verifies the $1 quote before checking
invisible sales; source behavior was not altered to make the fixture pass.

`EFFECTIVE-FLOW-VALIDATION.json` records tested source Git blobs/SHA256s, exact
counters, per-control outcomes and output hashes. Its compact publication format
omits repetitive mutant counters; the unchanged runner regenerates the verbose
receipt and normal/optimized logs. Timings, temporary paths and their log hashes
can differ on rerun; source identity and semantic outcomes must not.

No economic gain, native runtime composition, whole-package acceptance, field
frequency, full-game result, leaderboard effect, production change, or Kaggle
submission is claimed by this receipt.
