# Bounded late-route model: recovered source and consumer delivery

This is an optional research consumer, not the selected TITAN policy. It restores
`model_choice.py` byte-for-byte from source `d792813c1782fd022f1af90ecf0df0d3d56280f0`
and makes its evaluator binding, tests, and measured results reusable. The
original scalar experiment in PR10086, its README, results, archive, and tests
remain unchanged. The originally reserved model panel 9982201/9982219 was not
recovered; this delivery does not assign it an outcome.

## Callable and ownership

```python
from model_choice import wrap_model_sell

candidate = wrap_model_sell(
    existing_sell_actor, engine, oracle.simulate_bundle, oracle.Scenario,
    physical_replay.replay_routes, physical_replay.ReplayLimits,
    seconds=0.6,
)
action = candidate.act(observation, configuration)
```

At decision 577, the consumer evaluates the existing MAIN and milk-exit programs
only when the current program is one of those two and the original controller
reports compatible stored prefixes. The original decision at 433 is not delayed
or suppressed. The same live SELL actor retains its controller, planned sales,
pending goods, and history; it runs once after the decision. Speculation uses
independent copies of the Arlene producer through RILL's existing physical replay
and T04's existing oracle. No simulator, route generator, seller, or second live
controller is introduced.

This cheaper producer-only model is deliberately not JOINT's complete frozen-SELL
projection. Its objective is terminal OWN cash under currently visible shops and
explicitly zero external flows. Future buyers, weeds, rival trades, and rival
cash are not inferred. A model gain would not establish paired-game dominance.
Missing, partial, incompatible, tied, or errored results preserve the incumbent.
The cooperative 0.6-second / 284-decision model budget is not hard preemption or a
whole-agent guarantee: a dependency may return late. This delivery explicitly
consumes KESTREL's post-return completion correction from PR10113.

`model_panel.py` supplies source-bound entries to the existing `panel.py` loop.
The latter adds optional Python arguments for the entry factory, two arm labels,
and metadata. Its original CLI defaults, entry generator, recorder, serialization,
and atomic result writer are unchanged. `model_regression.py` runs only the two
model candidates on the known development regime and reads saved controls.

## Executed results

| Evidence | Executed outcome | Interpretation |
| --- | --- | --- |
| Recovery boundaries | 19 methods pass, zero failures/errors | Newly executed checks; not the unrecovered earlier 21-method report |
| Actual source consumer | 577 saved actions restored exactly; two 142-decision tails; actor/input unchanged | Conditional own-state model, not a game result |
| New development 9982401/9982419, Arlene/Apex, both positions | 16/16 games complete; control 7W/0T/1L, model 7W/0T/1L | All eight model cases have another existing route at 577 and are INACTIVE; all eight full paired transition digests match |
| Known development regression 9982019/Arlene, both positions | Two candidate games complete at 72,082 own / 70,108 rival; both match the original controls in every recorded transition | One mirrored known regime, not two independent validation wins; no control games rerun |

In the known regression the model actually executes 284 speculative decisions:
MAIN 75,052 versus incumbent milk-exit 75,383, so it keeps the incumbent. This
avoids the earlier scalar reversal's loss on that already-observed case. Modeled
cash is not realized cash. The old scalar result remains separately recorded;
none of these comparisons establish an improved default or held-out benefit.

The same 19-method consumer also passed from the relocated evidence package;
its full source/result report matches except for elapsed timings. This is
portability reproduction, not 19 additional independent tests.

There were 18 new attempts and 18 complete games in this recovery. The two
historical controls are reused references, not new attempts. The new panel's
maximum model-arm action was 84.86 ms, but no model was invoked there. In the
known regression the actual model portions were 494.48 / 531.53 ms and the whole
candidate action maxima were 509.45 / 546.13 ms. Initialization was measured
separately by the evaluator and is retained in the raw reports. These observations
are not broad latency guarantees. In `recovery-tests.json`, the very small
`choice.model_wall_seconds` times consumption of an already-computed report;
it is NOT tail-evaluation timing. The full-game measurements above include the
actual model call.

## Exact consumed sources

| Component | Git blob / source identity |
| --- | --- |
| Recovered model | `9c799addd18a1df86096bf321598dc834cd36ffc` |
| Original frozen SELL | SHA256 `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9` |
| Arlene | SHA256 `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4` |
| T04 oracle | `49640c27862d3d132c828fbafc6a8b4957527736` |
| Repaired RILL replay | `e299275048d241602541e3329631f169e4de7634`, PR10113 merge `a82365da6a1bf06cb9b78e7136702b348df918b3` |
| Official interpreter | Kaggle/kaggle-environments `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c` |

The recovered model bytes and original scalar sources have no decision changes.
The repaired replay dependency is an explicit new source pin, not silently added
to an old panel. `MODEL-RECOVERY-RESULTS.json` records all code/dependency hashes,
complete-game trace fingerprints, measured choices, and archive location.

## Reproduce from the retained evidence package

The evidence package includes `source/`, the exact existing `reference/` source
cache, `engine/`, `dependencies/`, original control records, all 18 new complete
traces, full reports, logs, and a SHA256 manifest. No credentials or provider
requests are part of reproduction. Use a new output directory; saved results
are not overwritten. Commands below are from the extracted package root on the
same Python 3.13 / Linux configuration. The C++ opponent can be rebuilt from the
retained source and existing include path:

```sh
B="$PWD"
S="$B/reference/revenue/kaggriculture"
D="$B/source"
E="$B/engine"
O="$B/dependencies/oracle.py"
R="$B/dependencies/physical_replay.py"
A="$S/cloud-frontier-policy/next-panel/vendor/apex"
g++ -O3 -std=c++17 -shared -fPIC -I"$A/source/include" \
  -o "$A/agent.so" "$A/source/policy.cpp" "$A/submission_bridge.cpp"

python -B "$D/test_model_recovery.py" --source-root "$S" --engine-dir "$E" \
  --oracle "$O" --physical-replay "$R" \
  --trace "$B/original/9982019-arlene-p0-frozen_sell_control.trace.jsonl.gz" \
  --report /tmp/model-recovery-check.json

# Label an intentional repeat as reproduction, not a fresh independent panel.
python -B "$D/model_panel.py" --source-root "$S" --engine-dir "$E" \
  --oracle "$O" --physical-replay "$R" --seeds 9982401,9982419 \
  --output /tmp/model-recovery-panel-new-directory

python -B "$D/model_regression.py" --source-root "$S" --engine-dir "$E" \
  --oracle "$O" --physical-replay "$R" \
  --original-results "$B/original/results.json" \
  --output /tmp/model-regression-new-directory
```

Generated entry files inside the saved game folders record the original absolute
execution paths. The drivers regenerate entries against the supplied relocated
source cache; do not execute historical entries as portable source. Source-pack
licenses and notices are retained unchanged under `reference/`; the new files use
Apache-2.0 SPDX notices and do not relicense those dependencies.

Next empirical work needs a separately frozen, observation-selected bank where
this model actually evaluates both tails and can choose differently. The eight
inactive cases are useful compatibility evidence, not grounds for another held
claim or default promotion. Original controller state must remain intact.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
