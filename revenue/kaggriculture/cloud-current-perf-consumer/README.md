# TITAN current performance consumer

Operation: `titan-current-perf-consumer-20260908-01`.

This is the additive acceptance/handoff root for the already-landed runtime helpers. It does **not** edit `cloud-execution-lab`, advance CURRENT, enable a strategy flag, run a provider submission, or create a second TITAN. WIDEFIELD remains the canonical package writer.

## Exact source boundary

The composer accepts only the funded-payback successor CURRENT:

- archive SHA-256 `499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e`
- `313471` bytes / `83` runtime files
- source-manifest SHA-256 `6350d80c2dc211e803da7741bba5f6b95b770e96827d65bb1343655754f25133`

It also pins the five canonical target Git blobs and every helper/patch Git blob. Any moved target fails before a patch is rendered. That is the collision/rebase boundary rather than permission to overwrite concurrent work.

Consumed source, without recreation:

- QUICKSTEP PR #10518: `seller_snapshot.py` blob `58ac31dada1c35b6dbaaaeef29fd83a0e52481ab` plus its exact `frozen_selected.integration.patch` blob `26682068bc43e817d50fdabbb9ab07850d1d5c48`.
- PULSE PR #10524: `observed_clone.py` blob `f810d53193d3035655a36c21021e18ba1d415916` at `scheduler.post_units` only.
- PULSE PR #10549: `plant_suffix.py` blob `95d05ff28aa79074d82bdc08ce4148d3ace1b13d` at immutable ALDER suffix-table construction only.
- TRACE-GUARD PR #10550: `worker-trace-lines.patch` blob `623fdec3859586f5dfab6f3597d868eaa2e1aad8`, targeting the exact pre-patch `deadline_adapter.py` blob `184ff5354451d764df95ffb5c952eecd0f4266f0`.

The generated builder delta adds only three source mappings: `seller_snapshot.py`, `observed_clone.py`, and `plant_suffix.py`. On this CURRENT that implies 86 runtime files after WIDEFIELD rebuilds the one canonical archive. ECON's funded-payback runtime/callback mappings and `fourth_quadrant=false` default are preserved.

## Use

From a fresh Commons checkout:

```bash
python -B revenue/kaggriculture/cloud-current-perf-consumer/compose_current.py \
  --repo . \
  --output /tmp/titan-current-perf.patch \
  --receipt /tmp/titan-current-perf.json
python -B revenue/kaggriculture/cloud-current-perf-consumer/test_current_perf_consumer.py
```

`compose_current.py` copies only the five canonical target files into a temporary directory, applies the exact landed patches there, performs the three narrow source transformations, compiles the resulting Python files, emits a unified diff/receipt, and verifies the input canonical files were not mutated.

`CURRENT-PERF.patch` is the rendered handoff for the pinned successor. WIDEFIELD should rerun the composer on fresh main immediately before canonical consumption; if CURRENT or any target blob moved, the composer intentionally fails and the patch must be rebased rather than forced.

## Accepted behavior evidence

This root consumes, rather than reruns, the peer evidence:

- QUICKSTEP: 11,504 retained calls with exact returned actions and completed state; measured hot-total reduction, no cold-timeout claim.
- PULSE projection: 17,256 calls/arm with exact actions/completed state and no caller mutation/fallback; no hosted or cold-timeout claim.
- COPPER composition: 96 fresh full-game executions / 32 matched triples with equal original traces and scores across baseline, QUICKSTEP, and QUICKSTEP+PULSE; 46,080 full-state comparisons found no differences. This is runtime-equivalence evidence, not stronger play.
- TRACE-GUARD: its focused source-bound suite preserves caller tracing/generator state while restoring line-event cancellation semantics; no game-strength claim.
- ASTRA-ELM independent old-current composition: the four runtime edits passed 20 packaged recovery/deadline regressions on exact `820ed99e…`; that is historical compatibility evidence only and is not represented as testing the funded-payback successor package.

Do not add peer speed percentages together. Do not infer the unresolved historical RPC timeout is fixed. Raw retained trajectories remain in participating-owner private storage.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
