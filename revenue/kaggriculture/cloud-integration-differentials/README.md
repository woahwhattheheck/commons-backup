# Fully funded seed-queue reductions

`seed_funding.py` supplies a small callable for an existing demand-valid seed
proposal. It certifies a sufficient condition under which reducing a BUY_SEED
quantity preserves every other order's current-market execution: the entire
original fixed-price queue is already affordable from observed post-unit cash,
without relying on any sale proceeds. It invokes no controller or simulator and
needs no rival private state or assumed rival order.

## Consumer

Use the caller's existing pinned mechanics module, exact post-unit observation,
original selected action, ALDER proposal and configuration:

```python
from seed_funding import select_seed_queue

# Inside the existing `dependent` / later-economic-order branch only.
# The existing seed-demand/route compatibility check must already have passed.
seeded, funding = select_seed_queue(
    mechanics, post_unit_observation, selected_action, seed_proposal, cfg
)
seed_reason = ("fixed_funding_certified" if funding["status"] == "certified"
               else "later_economic_order")
```

`certify_seed_funding(...)` returns the report without selecting an action.
`select_seed_queue(...)` returns `(detached_action, report)`: the supplied proposal
when certified, otherwise the original selected action or explicit
`fallback_action`. No arbitrary condition is added outside that existing branch.
The caller retains its seed-demand proof and ordered SELL stage. Do not reuse a
report on another observation, configuration or action; compute it for the
current packet. The module imports only the standard library.

This is an optional consumer for `cloud-execution-lab/integrated_selected.py`
source `843f6dbb7d564204802d54e1611fe912aea497df` (PR9997, merge
`b15af38473a7f5ab315753ffebda7aba5177aee2`). That source keeps every seed proposal
with a later HIRE, land, animal or product acquisition unchanged. The certificate
recognizes a strictly narrower fully-funded regime without changing the pinned
candidate, its archive, its parent, or a running comparison. ALDER's SeedBudget
and its route suffixes remain authoritative for seed demand.

## What is certified

The two actions must differ only by reductions of the same seed product at the
same effective order slots. Every non-market field and all other order slots
must remain equal. Costs use the supplied official CROPS seed prices, ANIMALS
purchase costs, hire Fibonacci costs with the actual daily counter/multiplier,
and remaining land prices. Repeated hires and acquisitions retain their order.
SELL revenue is given no funding credit. BUY_PRODUCT needs paired-flow pricing
and returns `not_certified`; truncated orders retain the engine's order limit.

Let B be the sum of original fixed-price requested costs and C the observed cash.
When C >= B, every fixed-price order is funded regardless of sales. Requested
animal costs upper-bound capacity-clipped costs. Reducing seeds changes neither
shed occupancy nor shared market inventory. Inducting over ordered slots leaves
the same hire/land/animal/SELL physical effects in both arms; fixed seed purchases
complete in both. For the same chosen rival queue, shared market state and rival
receipts also remain identical. The own current-market cash delta is exactly the
removed seeds' fixed purchase cost. Seed inventory is intentionally different.

This is a sufficient condition, not a maximal classifier. Unknown or unsupported
cases preserve the existing fallback; an uncertified queue is not declared
infeasible. The general `cloud-market-queue-delta/queue_delta.py` comparator
(PR9976, merge `f7629e07b0bfb87a7e7dbf95c0005e89af7da821`) remains the consumer
for explicit rival scenarios, partial fills and other queue effects.

The certificate covers only this market phase. It does not establish that seeds
are unnecessary, constrain later controller reactions to surplus cash, price
future workers, prove terminal improvement, or promote a policy.

## Executed validation

Fifteen new regression methods passed: 71 paired official-market cases / 142
complete `_process_market` calls. Seventy funded pairs preserve full non-seed own
state, rival state and shared market state, with the exact predicted cash delta.
One underfunded negative is rejected and returns the original action. No full
game, game seed, prior 79-method suite or prior seven-method integration suite was
run by this component delivery.

The funded discriminator starts with 1,000 cash and twelve prior hires: reducing
ten WHEAT seeds to three retains the same 233-cost HIRE and saves 70 cash. The
new underfunded discriminator starts with 300 cash: deleting the seed buy enables
the hire and changes final cash from 200 to 67. It is correctly not certified.
Other cases cover both seats, four rival queues, repeated hires, land, animals,
capacity clipping, mixed sales, repeated seed reductions, custom multipliers,
truncation, unchanged inputs and caller fallback preservation. These are
constructed post-unit mechanics cases, not reached game-state or strength claims.

Tests consume the existing official engine artifact `10005621438`, ZIP SHA-256
`06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`.
Engine revision: `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
`kaggriculture.py` SHA-256:
`bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.
The cache also contains `kaggriculture.json` and the upstream Apache-2.0 LICENSE.
No engine is redistributed here. The loader removes only the framework import
used by episode initialization; all original function bodies remain unchanged.
Tests never invoke initialization, random draws, network access or an exporter.

```sh
python -B test_seed_funding.py \
  --engine-source /existing/cache/engine/kaggriculture.py \
  --result /tmp/cedar-funding-results.json
```

`validation.log` is the original test output. `validation.json.gz.b64` contains
the complete original JSON report, losslessly gzip-compressed then base64-encoded;
`validation-summary.json` records both original and encoded-file hashes. Decode:

```python
import base64, gzip
from pathlib import Path
raw = gzip.decompress(base64.b64decode(Path("validation.json.gz.b64").read_bytes()))
Path("/tmp/cedar-recorded-validation.json").write_bytes(raw)
```

The original report binds the exact runtime and test source hashes, every paired
market comparison, counts and elapsed time. It is a local component result,
not a hosted CI or complete-agent runtime result. FINCH retains runtime profiling;
Claude retains game execution. The frozen selected policy is unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
