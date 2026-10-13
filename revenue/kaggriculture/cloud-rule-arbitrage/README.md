# T11 rule-backed market cycles

This lane supplies a callable transform over one authoritative base action:

```python
from cycle import RuleCycleTransform

transform = RuleCycleTransform()
action = transform.transform(observation, configuration, base_action)
```

`candidate.py::agent` applies it to T08's selected frozen SELL policy. The
transform never changes inherited farmer, hand, or market-order positions. It
may append paired `SELL FERTILIZER 1` / `BUY_PRODUCT FERTILIZER 1` orders only
when public inventory is deep enough inside the official `$1` plateau to remain
at `$1` after a conservative full rival withdrawal bound. Existing stock is
projected through the pinned unit helper and reserved for inherited sales first.

Why the narrower policy: the official engine quotes both seats before per-unit
commits. A solo `BUY_PRODUCT` then `SELL` round trip is exactly zero. A rival
same-slot buy can make it positive, but a rival same-slot sell can make it
negative at an integer price boundary. Current rival orders are not visible, so
that contingent case remains analysis only. The floor recycle is cash- and
stock-neutral while removing one public inventory unit because `$1` sales are
not admitted to market supply.

Development seeds `9830001`, `9830019`, and `9830037` were used. Held seeds
`9830101` and `9830119` remain untouched because the candidate made no action or
score change versus its frozen parent. See `RESULTS.md` and the raw JSON. This
research transform is callable but is **not selected for composition**.

Reproduce on a cloud runner with the repository's pinned official engine:

```sh
cd revenue/kaggriculture/cloud-rule-arbitrage
python -m unittest test_rule_arbitrage -v
python ../cloud-eval/evaluate.py \
  --engine-dir ../cloud-execution-lab/reference/engine \
  --candidate candidate.py \
  --opponent arlene=../cloud-titan-composition/arms/baseline.py \
  --opponent frozen_sell=../cloud-titan-composition/arms/sell.py \
  --seeds 9830001,9830019,9830037 --recheck-first \
  --output /tmp/development-candidate.json
```

No hosted replay, private opponent source, network service, credential, model,
Kaggle notebook, or upload is used by the policy.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
