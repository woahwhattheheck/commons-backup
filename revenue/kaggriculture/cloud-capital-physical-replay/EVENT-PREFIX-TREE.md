# Recursive declared-event prefix reuse

This optional optimization extends the existing `replay_routes(..., reuse_scenario_prefixes=True)` implementation. The previous source executes one prefix common to every supplied world, then runs every remaining world independently. The new source builds a prefix tree over the exact declared T04 event fields (`market_deltas`, `new_shops`, `new_weeds`). It executes every still-indistinguishable segment once per offered route and forks the **complete actor plus returned physical world** immediately before the first different event.

Worlds never rejoin after their declared histories diverge. Scenario labels remain evidence only. Unsupported or extended scenario schemas use the unchanged independent path. Default `reuse_scenario_prefixes=False`, route order, case/report fields, KESTREL completion checks, and selection-null behavior are unchanged.

## Executed results

The complete inherited and added test composition passes **51/51 methods**: 37 existing prefix/deadline methods and 14 new tree methods. New coverage includes exact six-world segmentation, no remerge, label-only equality, current-step divergence, unsupported-schema fallback, both player positions, scenario-order invariance, actor-local RNG, deep-checkpoint identity/cancellation, independent returned objects, and partial-budget behavior.

On the immutable DELVE226 integrated actor and six saved shop worlds, all **12 complete route/world case objects** match the saved references after canonical JSON normalization. The live actor and input are unchanged.

| Existing saved-bank execution | Decisions | Wall time |
|---|---:|---:|
| Prior flat-prefix implementation | 5,306 | 104.515s |
| Recursive event-prefix tree | 3,866 | 72.857s |

The tree removes **1,440 decisions (27.14%)** relative to the flat implementation and **2,050 (34.65%)** relative to twelve independent tails. Its exact branch steps are 287, 359, 431, 503, and 575. These two full-bank wall times were sequential on one cloud container, so the work-count result is exact while the observed 30.29% wall reduction is not presented as a controlled universal speedup.

A separate **nine-pair alternating** short-horizon native-T04 benchmark preserves every case field and reduces median time from 0.254822s to 0.228707s (10.25%), with decision counts 474 to 330. That is a constructed component benchmark, not game or whole-agent latency.

## Reproduce

From this directory beside the existing RILL evidence and the original flat source:

```sh
export OSPREY_RILL_EVIDENCE=/path/to/rill-evidence-root
python -B -m unittest -v \
  test_prefix_reuse test_completion_deadline test_event_prefix_tree

python -B benchmark_event_prefix_tree.py \
  --rill-evidence /path/to/rill-evidence-root \
  --flat-source /path/to/PR10286/physical_replay.py \
  --repetitions 9 --output /tmp/event-prefix-benchmark.json

python -B check_event_prefix_tree.py \
  --rill-evidence /path/to/rill-evidence-root \
  --arrival-evidence /path/to/arrival-sensitivity-root \
  --output /tmp/event-prefix-natural.json
```

`check_flat_event_prefix.py` produces the matched prior-source comparison. Use fresh output paths.

## Scope

No game was initialized, no seed was consumed, and no policy or route was selected. The six worlds are explicit conditional own-state models, not calibrated probabilities or paired rival trading. The optimization assumes the supplied actor fork includes its local random state and the injected simulator is the unchanged deterministic T04 consumer. External/global stochastic callbacks remain outside the opt-in contract.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
