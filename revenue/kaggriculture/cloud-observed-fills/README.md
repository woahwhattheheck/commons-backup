# Observed own-market fills

A standard-library consumer that distinguishes a submitted sale from an observed
quantity fill. It does not choose a policy, infer a price, or change an action.
Source is Apache-2.0. Existing T15, ASH continuation, selected SELL, producer and
feasibility implementations remain unchanged.

## Runtime contract

Import `observed_fills.py` only. Use one ledger per actor/match:

```python
from observed_fills import ObservedFillLedger, full_sale_verdict

ledger = ObservedFillLedger(max_states=4096, max_transitions=100_000)
# AFTER all action transforms, from the SAME final selected unit stage:
binding = ledger.record(
    observation, configuration, final_action,
    post_unit_shed=exact_post_unit_shed,
    post_unit_inventories=ordered_whole_carried_inventories,
)
# At the next decision, BEFORE that decision's worker actions:
result = ledger.observe(next_observation)
verdict = full_sale_verdict(result, previous_sale_slot, previous_requested_quantity)
```

`record` takes the observation and configuration before the final action, but
its shed and inventories must be the exact state AFTER that action's unit stage.
A pre-unit snapshot, speculative production envelope, or another controller's
projection is not interchangeable. Call `record` after the last market transform;
a same-step replacement supersedes the earlier recorded action. The result binds
the step, player and SHA-256 of the detached final action.

Before associating a verdict with a plan, match that binding and the recorded
slot, product and request to the actual plan emission. `full_sale_verdict` checks
the slot, SELL type and exact requested quantity; product/plan identity remains
with the consumer. True proves the requested quantity sold under the supplied
snapshot contract; False proves a short fill; None is unknown. Do not coerce
None to success. This is past-fill evidence, not positive future feasibility.
Combine it with the existing current continuation check; do not replace ASH's
callback, COORD's physics, or the caller's valid fallback. The ledger itself
neither retires a plan nor changes an order.

The next observation must be from the same actor at the adjacent decision.
Same-step reads stay pending. Missing steps, invalid clocks and mismatched
snapshot evidence return unknown. The ledger accepts a consistent `step`, or
uses `day * turnsPerDay + hour` when `step` is absent.

At a daily boundary, supply each worker's whole carried-inventory mapping in the
actual automatic-deposit order, with each mapping's original item order. The
ledger applies those deposits AFTER the market with capacity clipping. Missing
inventories at such a boundary remain unknown. At default decision 718 to 719 it
does not invent a terminal automatic deposit or salvage.

## What the quantity model proves

`reconcile_shed_fills(post_unit_shed, submitted_action, next_shed,
configuration=None, *, after_market_deposits=(), max_states=4096,
max_transitions=100_000)` also works statelessly. An empty deposit sequence means
known no deposits; None means unknown. The CLI accepts these keyword arguments
as one JSON object:

```sh
python observed_fills.py input.json --output reconciliation.json
```

Exit 0 means a compatible exact or ambiguous result; exit 2 means unknown.

The bounded dynamic program retains the complete own shed vector, shared
capacity, original market positions, parser behavior, slot truncation and the
pinned interpreter's per-slot iteration ceiling. SELL quantities are determined
by available own stock. Purchases retain every quantity from zero through the
request/capacity bound. Cash and rival-dependent quotes are deliberately not
used: this is a superset of possible actual paths, not a claim every retained
path is executable. HIRE, BUY_LAND and BUY_SEED fills are not inferred from shed
stock. No hidden rival state, seed, future action or cash-delta attribution is
used. Every reported cash receipt is null.

Only paths matching the next own shed after ordered deposits contribute to the
per-slot quantity intervals. Those intervals are correlated: their endpoints
must not be combined into a fictional joint path. A singleton is an exact
quantity conclusion conditional on the input contract. `reconciled` concerns
shed-changing orders only; it does not certify non-shed purchases or cash.
Contradictory evidence and exhausted state/transition budgets return unknown,
not a sampled guess. Budgets limit work; they are not a whole-agent time bound.

## Executed validation and reuse

The retained run passed 32 methods, with zero failures/errors/skips. It includes
42 constructed official-market cases across both seats and 42 separate
uninstrumented controls. Evaluation-only delegates record successful per-slot
commits; every full traced state equals its uninstrumented control. Every actual
shed-changing fill lies inside the runtime's reported interval. Four cases also
execute the original automatic-deposit helper. The runtime receives only own
snapshots/actions, not the evaluator's rival inputs or cash outcomes.

Coverage includes clipped/repeated sales, paired rival quotes, shared purchase
capacity, unknown affordability, market slot truncation, floor sales with no
shared-inventory admission, ordered end-of-day overflow, round-trip ambiguity,
clock gaps, final-action binding, budget exhaustion and a JSON CLI invocation.
The floor-sale witness recognizes the sale quantity despite unchanged shared
market inventory. The buy-one/sell-one wheat round trip correctly remains
ambiguous from shed evidence at both zero and sufficient cash.

Maximum measured warm reconciliation was 0.059468 ms on these small fixtures,
not a whole-agent or worst-case guarantee. No full games, held seeds, new source
exports, policy-selection changes or hosted-strength claims are included.

Reuse the existing engine cache from artifact **10005621438**. No new export or
network fetch is needed. From repository root:

```sh
python revenue/kaggriculture/cloud-observed-fills/check_observed_fills.py \
  --engine-loader revenue/kaggriculture/cloud-execution-lab/reference/evaluator/loader.py \
  --engine-cache /path/to/existing/engine \
  --json-output /tmp/observed-fills-results.json
```

The test verifies all three existing engine-file SHA-256 values before importing
the supplied loader. Official source is
[Kaggle/kaggle-environments@28b6d8af](https://github.com/Kaggle/kaggle-environments/tree/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c),
Apache-2.0: `kaggle_environments/envs/kaggriculture/{kaggriculture.py,kaggriculture.json}`
and `kaggle_environments/utils.py`. No vendor code is copied into this component.
The local run used the same cache and the existing artifact's loader; its exact
hash, runtime/test hashes and all engine hashes are in `validation.json`.

`validation.json` preserves the original full 42-case report and test log as
lossless zlib/base64 payloads, with sizes and hashes. Decode from this directory:

```sh
python - <<'PY'
import base64, hashlib, json, pathlib, zlib
packet = json.loads(pathlib.Path('validation.json').read_text())
for name in ('results.json', 'test.log'):
    entry = packet['payloads'][name]
    raw = zlib.decompress(base64.b64decode(entry['data'], validate=True))
    assert len(raw) == entry['bytes']
    assert hashlib.sha256(raw).hexdigest() == entry['sha256']
    pathlib.Path('decoded-' + name).write_bytes(raw)
PY
```

Original tested runtime SHA-256:
`8439d571028e5613bfcd70cfa1428ee86b1c17c89a1297288191c2a833f38857`.
Original tested suite SHA-256:
`cddde4302305457703b0d0d75d6f4e7086d146827c320ab68428e3d77e77589c`.
The scope is quantity reconciliation for downstream consumers, not a change to
T15's source freezes, payoff tables, continuation optimizer or selected default.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
