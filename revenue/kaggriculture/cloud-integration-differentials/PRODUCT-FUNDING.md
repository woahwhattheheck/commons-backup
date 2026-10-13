# Optional public-price funding for seed reductions

`seed_funding.select_public_seed_queue` extends the existing fixed-funding
certificate to bounded WHEAT and FERTILIZER purchases. It consumes an already
valid seed-demand reduction, then checks whether the original queue can fund
all its requests even at a conservative public-price bound. It does not infer
seed demand, choose a producer, simulate an opponent, or value future cash.

The default `select_seed_queue` and `certify_seed_funding` behavior is unchanged:
`public_product_bounds=False`. No selected policy, frozen source archive, game
panel, or JUNIPER/CYPRESS implementation is replaced by this extension.

## Use the existing integrated callback

PR10015 supplies the `seed_queue_selector` seam after ALDER's demand check and
before the existing projection/arrival/SELL stages. Reuse that seam, not another
wrapper or controller:

```python
import sys
from pathlib import Path

root = Path('revenue/kaggriculture').resolve()
sys.path[:0] = [str(root / 'cloud-integration-differentials'),
                str(root / 'cloud-execution-lab')]
from integrated_selected import make_agent
from seed_funding import select_public_seed_queue

candidate = make_agent(seed_queue_selector=select_public_seed_queue)
control = make_agent(seed_queue_selector=None)
# Each instance belongs to a separate actor/match. Call only its own act().
action = candidate.act(observation, configuration)
```

This is an opt-in comparison contract. This component suite does not claim an
executed complete integrated-agent comparison or downstream ingestion. The
seam is available from main merge
`4f81700446b64236c14a4a4c1e6afddc045b44b9`; its earlier joined result is distinct
from the new product-bound evidence below. `integrated_parent.py` also disables
SELL and is therefore not the isolated control for this callback.

Direct use after an existing demand proof:

```python
chosen, report = select_public_seed_queue(
    mechanics, post_unit_observation, selected_action, seed_proposal, configuration
)
```

The callback returns a detached proposal only when certified; otherwise it
returns the original selected action. The existing entry point also accepts
`select_seed_queue(..., public_product_bounds=True, fallback_action=...)`.
The post-unit observation must include the visible `market.inventory` and any
resolved `market.params` for nonzero product orders. No rival action, private
inventory, seed, or cash is a runtime input.

## Bound and scope

The pinned official engine processes each market position in per-unit lockstep:
quote both actors, commit both, then continue that position. Product purchases
quote at shared inventory minus one and are not stopped at zero inventory.
Relevant primary source is the unchanged
[market stage and commit functions](https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture/kaggriculture.py#L544-L686).

Let `C` be shed capacity, `i` the zero-based current slot, `I[p]` the visible
initial inventory of product `p`, and `Q_i[p]` the sum of
`min(requested_quantity, C)` over our purchases of that product through slot i.
A single BUY_PRODUCT order cannot fill more than C units: no same-actor sale or
worker action interleaves that order. A conservative bound for rival purchases
through the current slot is `(i + 1) * C`. Ignoring every sale gives a lower
bound on the quote inventory:

```text
L_i[p] = I[p] - Q_i[p] - (i + 1) * C
unit_price_upper_bound = market_price(p, L_i[p], resolved_public_params)
order_cost_upper_bound = min(requested_quantity, C) * unit_price_upper_bound
```

`L_i` may be negative. A price at inventory zero is not an upper bound. Each
product is bounded independently, deliberately ignoring cross-product capacity
competition and the rival's need to clear stock between slots. This may reject
some affordable queues; it cannot make an accepted price bound smaller.

Supported engine price shapes with finite, nonnegative amplitudes and positive
normalization are monotone in inventory. Unknown shapes, nonmonotone parameters,
missing inventory, unsupported purchases, or malformed requests preserve the
original action. Full requested fixed costs plus bounded product costs must fit
observed own cash, with no credit for any SELL receipts.

For the same chosen rival queue, all original requests are then unconstrained
by cash. Reducing an unnecessary seed purchase changes neither shed occupancy
nor shared inventory, so induction over market slots preserves both actors'
non-seed execution, capacity clipping, shared book, and rival cash. Our extra
cash is exactly the removed seeds' fixed cost. The certificate establishes this
market phase only. It does not prove seed demand, future controller equivalence,
terminal profit, game wins, or a leaderboard improvement. Unchanged later HIRE
or acquisition decisions on other turns can still react to the saved cash.

The original report field `original_fixed_cost_upper_bound` remains the fixed
subtotal. With product bounds, `original_total_cost_upper_bound`,
`product_cost_upper_bound`, and per-slot `public_product_bounds` are added.
Successful reason is `original_queue_fully_funded_with_public_product_bounds`.
Without the opt-in flag, action and report remain identical to PR10000.

## Executed evidence

New component suite: **17 methods, zero failures/errors, 96 certified paired
market cases**, both seats, with 196 full official market-stage calls in total.
The total includes one rejected negative pair and two instrumentation-control
calls. Another 240 comparisons establish exact default action/report parity
against the original PR10000 source; they do not replay its old test panel.
All constructed inputs, both actions, evaluation-only rival queues, full states,
actual product commit prices, and reports are retained losslessly.

Concrete cases:

* Funded BUY_SEED WHEAT10 to3, then BUY_PRODUCT WHEAT3 and HIRE: both seats retain
  all non-seed results, with cash9588 to9658, saving70. The sufficient total cost
  bound is450; product prices are bounded rather than forecast.
* Inventory-zero negative: visible FERTILIZER inventory0, capacity10, original
  cash4300, seedWHEAT10 and FERTILIZER2, with an evaluation-only prior rival
  FERTILIZER10 purchase. A naive price(0) calculation says4300 suffices. Actual
  original fills one product and ends2098; removing the seed buy fills two and
  ends96. The new bound uses inventory minus22, requires4308, and keeps the
  original queue. This is not counted as a certified saving.

The positive grid covers both products, both seats, below-zero/floor/ordinary
inventory, paired rival buys and sales, repeated buy/sell slots, capacity-clipped
requests, and every supported price shape. Invalid-input and unknown-bound cases
retain fallback. Instrumented and uninstrumented complete-market outputs match
on the explicit control.

These are constructed post-unit transitions: **zero complete games, no game
seeds, no initialization/RNG, no whole-agent runtime or strength claim**. Python
3.13.5/Linux execution, raw test log, exact source hashes, and original elapsed
measurement are in `PRODUCT-SUMMARY.json` and `PRODUCT-TESTS.log`. The existing
engine artifact10005621438 was reused; no new exporter or workflow was created.
The test removes only an unused unavailable initialization import; all official
market function bodies and constants remain unchanged.

## Reproduce or inspect

Use the already-cached official engine file, SHA256
`bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.
Retrieve the original certificate for the default comparison:

```bash
git show 5b4b4b1d40b3fc6f39065f6553befd71f652c5dd:revenue/kaggriculture/cloud-integration-differentials/seed_funding.py > /tmp/cedar-original.py
python -B revenue/kaggriculture/cloud-integration-differentials/test_public_product_funding.py \
  --engine-source /path/to/existing/engine/kaggriculture.py \
  --original-source /tmp/cedar-original.py \
  --result /tmp/product-results.json.gz
```

Inspect the original saved output without executing transitions:

```python
import base64, hashlib, json, lzma
from pathlib import Path
p = Path('revenue/kaggriculture/cloud-integration-differentials')
encoded = (p / 'PRODUCT-RESULTS.json.xz.b64').read_bytes()
assert hashlib.sha256(encoded).hexdigest() == 'b9f39444f218f631403d566d283d80649efcd49434664d30524cacebbddc892c'
compressed = base64.b64decode(encoded)
assert hashlib.sha256(compressed).hexdigest() == '5d1e24911804cf96b88a0171bad9403a1042035370b64c68c32d2ebab3b31d71'
raw = lzma.decompress(compressed)
assert len(raw) == 2980937
assert hashlib.sha256(raw).hexdigest() == '4941547a370f610cfaed3c10c33f9a503048a5c047bcff92e352c17bdbe2de50'
report = json.loads(raw)
assert report['tests_run'] == 17 and report['certified_pairs'] == 96
```

Source pins: original certificate PR10000; official engine
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; new callback SHA256
`bf6c676f06e8b68328ae17c990bb119324b1b4f73d1cfd2ec61941aea1d7cfbf`;
new test SHA256
`0f92bc60e6afb32e2efedfa9269ae3cb239ab58f50cd27c4fc2f26a94e8a3ca6`.
All earlier CEDAR, JUNIPER, CYPRESS, QUEUE, and executor evidence retains its
original scope and attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
