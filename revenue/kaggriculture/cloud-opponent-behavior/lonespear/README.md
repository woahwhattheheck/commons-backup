# Lonespear public hiring-prefix model

A small public-state model of the exact lonespear v18 source and an offline
consumer of six existing T14 development traces. It is not an opponent-identity
classifier, a new opponent, a replacement hiring controller, or selected TITAN.

## Runtime interface

```python
from behavior import predict, observed_fill, propose_delayed_wheat_sale

hypothesis = predict(observation, configuration)  # defaults to the rival position
filled = observed_fill(previous_observation, observation, actor=1-observation['player'])
proposal = propose_delayed_wheat_sale(
    selected_action, hypothesis,
    shed_wheat=actual_post_unit_shed['WHEAT'],
    retained_wheat=committed_wheat_reservation,
)
```

`predict` reads only public farm tiles, cash, hands, hires-today, clock and
configuration. It imports no policy, retains no hidden inventory, and accepts
no rival action or outcome labels. Its predictions are conditional on the named
source: observing a matching feature vector does not identify an unknown rival.
The model supplies the exact leading HIRE request count and conditional fills,
and an interval for the possible following wheat request. Unknown/malformed
public inputs stay `status="unknown"`, not a fabricated zero.

`observed_fill` measures successful hires from consecutive, same-day public
hand/count changes. Daily reset, missing frames and inconsistent deltas remain
unknown. Public net cash is the entire turn's result, not hire-only spending.

`propose_delayed_wheat_sale` preserves the selected farmer/hands, quantities and
all other market indices. It only moves one existing wheat sale in a sale-only
queue to an unused position after the possible feed slot. It checks the supplied
post-unit wheat reservation and the market-slot limit. Unsupported inputs return
the complete original action. The output is an experimental proposal requiring
full paired-queue valuation; it is **not** an economic-improvement certificate.

## Source and inputs

Original lonespear: `lonespear/kaggriculture` commit
`774b26093ccf4246525517d48420349b841b6e50`, MIT, `main_v18.py` SHA256
`eb5b5f59a8ec2d40b77cc99d4ffe3b932136fdcf9f6b6e168726b7f07ab47cb0`.
The source is unchanged. The runtime model was independently implemented from its
public request rule. Assignment-mode variants are one source lineage, not
independent opponents; the retained T14 records use its greedy adapter.

T14 input: PR9975 merge `5be6099f5ab2b3a20855bdee1e1e42f336eab678`,
`cloud-policy-portfolio/revision2/artifacts/`. The original full-trace XZ SHA256 is
`f26238195253c10d087f8e47cc92b4fe47e3b429c6fee398b165747f5fdad133`.
The original trace codec is consumed unchanged and checked by hash. The extractor
selects only SELL controls: development-v2 seed9881001, development-v3 seeds9881019
and9881037, both positions. It does not analyze any held/conditional-validation
records or count earlier v1 copies again.

The existing committed data is downloadable through Actions artifact
**10037073246**, run **34175317253**, produced by the source-only PR10025 workflow.
ZIP SHA256 `4c7bc03c383ba73d0687156f864b7d529eacd63bfa8a755b66d90805a3b31335`.
Its manifest binds all 243 original files and the tar archive to the source commit.
The retrieval job copied bytes only: no policy import, new opponent fetch, game,
installation or owner-machine execution. Reuse this artifact rather than rerun it.

The unchanged engine is `Kaggle/kaggle-environments` commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. Existing engine artifact10005621438
and source/loader artifact10030763484 also remain usable. Exact hashes are in
`SOURCE-PINS.json`; preserve their original license scopes.

## Offline commands

From this directory, with the original portfolio extracted to `$PORTFOLIO`:

```sh
python extract_development.py --portfolio "$PORTFOLIO" --output dev-inputs
TITAN_LONESPEAR_SOURCE="$LONESPEAR" TITAN_EVALUATOR="$EVALUATOR" \
  TITAN_ENGINE="$ENGINE" python -m unittest -v test_behavior
python analyze_development.py --inputs dev-inputs --output analysis \
  --evaluator "$EVALUATOR" --engine "$ENGINE"
```

`LONESPEAR` points to the exact source above; `EVALUATOR` to the retained
`cloud-eval/evaluate.py`; `ENGINE` to its pinned cache. Without environment
variables the tests use those normal repository-relative source locations.
The small `base-frame.json` fixture is a retained engine initialization observation
from the earlier IRIS archive; synthetic tests modify copies, not original data.

The analysis reconstructs inventory from recorded actions solely for offline
receipt attribution. Every original own-inventory checkpoint and cash transition
is checked. Rival private stock and recorded actions never enter `predict`.
The receipt instrumentation temporarily wraps the exact engine in a sequential,
isolated module; it is not a thread-safe shared service or runtime dependency.
Outputs use new directories, leaving source evidence unchanged.

## Recorded results

Twelve focused tests pass, including 240 exact-source request comparisons and
96 unmodified official-market prefix-fill comparisons; public negative controls,
private-data independence, history resets, reservation/slot limits and unchanged
worker/other-sale indices are covered.

The six original development traces contain 4,314 decisions across three seeds.
All request predictions match. All 1,746 requested hires filled on their 324
request turns. All 4,134 available within-day public fill deltas match. These are
repeated observations in six paired trajectories, not 4,314 independent trials.

Recorded feed requests total7,348 units, actual fills7,344. The two partial cases
are mirrored seed9881019 step197 (hour5), **not** an observed HIRE-prefix failure:
seven wheat units requested, five bought for174 from198 cash, leaving24 when the
next35 quote fails. Later sales bring final cash to915. A positive end-of-turn
cash change therefore does not prove that an earlier purchase fully executed.

The market-response discriminator uses development-chosen step697 across all six
traces. It preserves complete recorded queues except the one moved wheat sale.
Own/rival cash changes are +17/−17 on9881019 and+22/−22 on9881037 in each position.
On9881001 the rival instead sells wheat, yielding−70/+70 and−47/+47. All final
private inventories and shared market inventories match their paired controls.
Removing the actual rival feed order eliminates the positive changes. Late-hour,
low-cash and already-staffed public controls leave the selected action untouched.

The blind delay has negative aggregate relative cash across this small development
set and is **not selected**. The reusable result is the exact HIRE timing/count
constraint; a caller still needs justified rival-flow scenarios to value a response.
Complete reached states, full own/rival receipts, public telemetry and negative
cases are retained in the delivery archive, with source bindings in the manifest.
No new full game, seed, held evaluation, Kaggle write or rating claim is created.

`TIMING.json` measures only the public detector on retained observations, not a
whole agent or RPC. `RESULTS.json` retains exact counts, source pins and paired
turn deltas. Original T14 outcomes, source owners and selected SELL remain intact.

## Complete delivery archive

`TITAN-IRIS-Lonespear-D-20260907.zip` contains this source, the six selected
development traces, complete paired-turn receipts and public predictions, the
small exact test-dependency closure with original licenses, and validation logs.
It excludes held/conditional-validation traces and unrelated portfolio data.
`BUNDLE.md` gives offline commands using its relative paths. `MANIFEST.json`
covers every other member. The separate `DELIVERY.json` records the ZIP hash
and its saved Library location. The runtime source remains commit108e0d17; the
archive is a source/evidence delivery, not a new policy evaluation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
