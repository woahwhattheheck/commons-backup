# Redundant-hire selected-action proposal

A bounded T10 economic component for the existing producer, not another TITAN
entrypoint or release. It reuses the caller's mechanics and chosen route. No
producer, market simulator, or future-price model is constructed.

## Use

After the existing frozen SELL producer has returned its action exactly once:

```python
from redundant_hire import propose_redundant_hires

selected = policy.act(observation, configuration)
controller = policy.controller
proposal, report = propose_redundant_hires(
    scheduler.m, observation, configuration, selected,
    route=controller.R[controller.cur],
    route_id=controller.cur,
    route_switch_steps=[item[0] for item in scheduler.parent.DECISIONS],
)
```

The function returns a detached complete action and diagnostics. An unproven
case preserves the supplied action. Caller adoption is a separately evaluated
economic choice: `changed` establishes the narrow physical-route conditions
below, not arbitrary future cash, opponent-response, or win equivalence.
The source contract is the Arlene route plus its observed weed/no-op repair.
Do not pass an old tape from a different worker controller and infer compatibility.

Current worker actions are applied once to detached own state to locate actual
hire spawns. No rival private state, future observation, episode seed, or result
is read. Only the effective market slots are inspected. All original hires must
already be affordable; active non-hire orders, future hires, potential route
switches, incomplete routes, and unsupported removed-worker tasks preserve the
original. Removed orders become zero-quantity SELL slots, never compacted queues.

Removed trailing new workers can only move, pass, or duplicate watering. Each
watered crop must remain structurally untouched, unexpired, and either already
watered or watered by a retained worker before the same daily reset. Harvest,
fertilizer and other operations on those crop tiles are not assumed harmless.
Visible weeds and crops that can decay into weeds retain their workers. The
caller still needs economic evaluation: extra cash can affect later purchases,
and publicly changed hand counts can affect a responsive opponent.

## Executed results

Runtime SHA-256: `a881284d6b59366536ebc5e77f0f7c7f2923599dfb8588fd8b1ed6166bd51483`.
Nineteen focused methods pass, with 746 complete official-interpreter transitions.
Among 240 generated short-route cases, 120 accepted proposals retained exact
post-reset state excluding money and saved precisely the reported wage.
Two initial test-fixture assumptions were corrected without changing runtime:
negative lifespan means no expiry in the engine, and `_new_farm(True)` becomes
float `1.0`. The initial failing log is retained alongside the corrected run.

Four new full treatment games used our already-consumed ADMISSION development
seeds 9957001 and 9957019, both positions against intact Arlene. Original frozen
SELL controls were reused, not rerun. Both treatments and controls finish 2W/0T/2L;
every treatment adds exactly 5 own cash and 0 rival cash. These are two mirrored
seed regimes, not four independent regimes. No held or leaderboard claim.

All 2,876 full action/bank rows were compared to retained control records. The
only authored action difference in each game is HIRE slot 1 at decision 121;
every other complete action on both sides matches. Own cash is exactly +5 from
that decision through terminal, while rival cash always matches. The function
contains no rule keyed to 121: it locates that hand's redundant WATER tasks at
129/131/136 and the retained WATER tasks at 138/136/136 from the actual route.

Across 216 calls in those games, the proposal's largest measured duration was
2.347 ms; the four active calls had median 0.590 ms and maximum 0.891 ms. Largest
complete candidate call was 154.920 ms, largest candidate RPC 155.854 ms under
the existing evaluator's 1-second limit. Those include the frozen SELL call and
telemetry writing; import/factory startup is separate. These are observed cloud
measurements, not a hard bound or a speed ratio against DOCK's older environment.

This experiment used frozen SELL `32c8610c` and Arlene `1dc166ae`, **not** the newer
canonical 58f8e6c1 package. It preserves and narrows DOCK's previously delivered
full-shift hiring mechanism; it does not replace DOCK's original source, tests,
40-game evidence, or cash-trough fix. No canonical runtime, feature configuration,
archive, or current checkpoint was modified. No new game seed was reserved.

## Reproduce the component checks

Use an existing Commons source and official engine cache; no download is made:

```sh
export TITAN_REPO_ROOT=/path/to/commons
export TITAN_ENGINE_DIR=/path/to/pinned-engine
python -B test_redundant_hire.py --report unit-results.json
```

The accompanying saved package includes exact new sources, test logs, four full
new trajectories, candidate telemetry, source identities, retained baseline
records, a reached own-observation example, and the experiment/analysis scripts.
Those scripts record their original cloud paths; the equivalent portable
selected-action binding is shown above. The official evaluator and source
closure are existing repository inputs, not a new executor implementation.

## Delivery state

NOT_LANDED. GitHub `create_blob` returned: "This tool call was blocked by OpenAI
because we couldn't determine the safety status of the request." No blob/commit
was returned and the blocked upload was not retried through another encoding or
write path. This package is a completed local implementation and measured result,
not a main, checkpoint-consumption, hosted-CI, or deployment claim.

## Attribution

Apache-2.0. Existing Arlene controller/routes, frozen SELL scheduler, official
engine and DOCK T10 mechanism remain attributed to their original authors.
The new work is the bounded selected-action proposal and its source-specific
component/full-game evaluation. Licenses accompany the retained input closure.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
