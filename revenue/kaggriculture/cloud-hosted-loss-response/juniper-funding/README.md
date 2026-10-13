# Optional funding selection on the existing T13 seed wrapper

The existing `seed_main.make_agent` now accepts `seed_queue_selector=None`.
The default remains the original ALDER demand-only seed reduction over the
unchanged frozen SELL policy. Supplying CEDAR's existing `select_seed_queue`
adds a current-market funding check only when a reduced seed order precedes
HIRE, BUY_LAND, BUY_ANIMAL or BUY_PRODUCT. No new controller, certificate,
seller, scheduler state or market model is introduced.

## Use

```python
from pathlib import Path
import sys
root = Path('revenue/kaggriculture').resolve()
sys.path.insert(0, str(root / 'cloud-hosted-loss-response'))
sys.path.insert(0, str(root / 'cloud-integration-differentials'))
from seed_main import make_agent
from seed_funding import select_seed_queue

candidate = make_agent(root / 'cloud-hosted-loss-response',
                       seed_queue_selector=select_seed_queue)
action = candidate(observation, configuration)
report = candidate.seed_funding  # None when no dependent proposal was inspected.
```

Keep one callable per actor and match. Its existing `.policy`, `.controller`
and `.budget` remain available. The callback receives detached
`(mechanics, post_unit_observation, selected, proposed, configuration)` and
returns `(action_dict, report_dict)` exactly as in the PR10015 integration.
No callback preserves the old T13 behavior; this differs intentionally from
PR9997's conservative dependent-order default. `enabled=False` disables seed
trimming entirely. `sell=False` still uses the same intact-Arlene option.
The existing singleton entrypoint is unchanged; the supplied observations must
include the evaluator's explicit step.

The named file callables in `arms.py` support the existing evaluator:
`agent` is fixed-funded seed+SELL, `legacy` is original demand-only seed+SELL,
and `sell` is frozen SELL without the seed stage. All use the same existing
factory and retain the scheduler's planned-sale persistence. There is no
PR9997 cap producer or generic selected-action seller in this comparison.

## Validation

Thirteen new joined test methods pass on both the source-frozen fixed-only
certificate and the current-main certificate (Git blob
`3d0c19cdf9f1260f56be3f6a7beb191b37b3d568`). Each checkpoint executes twelve
complete official market phases, separately from the full games below.
Constructed funded 17-to-3 WHEAT cases preserve HIRE and non-seed state while
saving 140 in-game cash in both seats. With only 300 cash, optional funding
preserves the original queue and 130 remaining cash; legacy trimming would
activate an additional HIRE and leave 67. Current PLANT accounting, deposit/sale
order, truncated queues, caller-copy isolation, no-callback/disabled behavior,
original exception propagation, and one real parent call are covered.

```sh
python -B revenue/kaggriculture/cloud-hosted-loss-response/juniper-funding/test_join.py \
  --engine-dir /path/to/existing/pinned/engine \
  --report /tmp/juniper-join.json
```

A separate exact-old-wrapper comparison uses both saved 719-input development
prefixes: 1,438 comparisons / 2,876 actual calls. Every output action, planned
and pending sale state, selected route, budget event and caller input matches
old blob `75d20f2f35693687cc4969536e8107d36d403831` when the callback is omitted.
This is compatibility replay, not another game panel.

### Six complete development games

Source frozen before seed 9989001, both seats versus intact Arlene, three arms:

| Arm | Own cash | Rival cash | Margin | Both-seat result |
| --- | ---: | ---: | ---: | --- |
| Frozen SELL | 89,456 | 89,033 | 423 | 2 wins |
| Legacy seed+SELL | 89,696 | 89,033 | 663 | 2 wins |
| Fixed-funded seed+SELL | 89,696 | 89,033 | 663 | 2 wins |

Both seats mirror one development regime, not two independent samples. All
six games complete 719 decisions without a timeout/error. The two seed variants
have identical complete action sequences and same-seat evaluator trace digests.
Their only action changes from frozen SELL are WHEAT purchases at step 600
(17 to 2) and 624 (9 to 0). The inherited seed improvement contributes +240;
this panel establishes **no additional gain or win flip from the funding check**.
Maximum funded actor call is 61.33 ms; maximum funded RPC is 62.32 ms in this
cloud execution, not hosted timing or a comparative speed claim.

The games consume unchanged scheduler SHA256
`32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`,
ALDER budget `455024a4179a95ad597492e1f4b94de7bd3bfe7a3a88fd0dce46001f629ec3cd`,
and DELVE's fixed-only certificate
`249ad9fd46625088bfb8e1ab977862701aabf7bbe48aa3fbc3e2f58e2c84fd85`.
The later current-main certificate check is not substituted into those game
results. Engine source is pinned to 28b6d8af / package 1.32.7.

## Complete evidence and next consumer

Library archive `TITAN-JUNIPER-frozen-SELL-funding-9989001.zip`, Files ID
`file_0000000014dc81f59cf8bb8d18e55876`: 2,264,736 bytes, 95 members,
SHA256 `a924fa25c889f8ece5beef1a1b33afdcb699395eff6f4f48fa356f39eea60618`.
It includes the exact frozen runtime/engine, all six original result and frame
files, source freeze, both dependency-check logs, old-wrapper compatibility
source/output and reproduction scripts. All 94 manifest entries verify; all
six saved frame sequences reproduce their complete evaluator trace digests.
The original DELVE source package and peer policy files remain untouched.

T08/cloud-model-lab can evaluate these direct frozen-SELL arms on its next
separately registered shard. Compare both legacy and funded seed variants
against frozen SELL; comparing only the two seed variants cannot measure the
inherited seed gain. No held validation, hosted rating, selected-default change,
new workflow, upload or new spend is claimed by this delivery.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
