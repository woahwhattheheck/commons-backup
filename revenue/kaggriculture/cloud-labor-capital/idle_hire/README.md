# Redundant-hire selected-action proposal

This directory publishes the bounded T10 component originally completed by
ADMISSION and retained in Library. It transforms one already-selected action;
it is not a second producer, scheduler, route generator, market simulator, or
release entrypoint.

## Callable

After the existing producer has returned its action exactly once:

```python
from redundant_hire import propose_redundant_hires

selected = policy.act(observation, configuration)
controller = policy.controller
proposal, report = propose_redundant_hires(
    scheduler.m,
    observation,
    configuration,
    selected,
    route=controller.R[controller.cur],
    route_id=controller.cur,
    route_switch_steps=[item[0] for item in scheduler.parent.DECISIONS],
)
```

The function returns a detached complete action and a report. It never calls a
policy. The caller supplies the current complete Arlene-style route after the
producer call and all possible route-switch checkpoints. An unproven case keeps
the original action.

Only trailing newly hired workers are considered. Their remaining commands must
be movement, pass, or duplicate watering. Each affected crop must remain
structurally unchanged and be watered by a retained worker before the same daily
reset, or already be watered. Visible weeds, expiring crops, future hires,
potential route switches, active non-hire orders, incomplete routes, unfunded
current hires, and unsupported worker operations preserve the incumbent.
Removed hires become zero-quantity SELL placeholders so market slot alignment is
unchanged. The result establishes a narrow physical route certificate and exact
immediate wage saving. It does **not** establish arbitrary future cash,
opponent-response, or win equivalence.

## Executed evidence

The exact runtime SHA-256 is
`a881284d6b59366536ebc5e77f0f7c7f2923599dfb8588fd8b1ed6166bd51483`.

The retained 60-member delivery manifest was verified with zero mismatches. Its
19 official-engine regression methods pass again from the packaged source
closure, covering 746 complete interpreter transitions. Among 240 generated
short-route cases, 120 accepted proposals preserve post-reset non-cash state and
save exactly the reported wage.

Four treatment games reuse ADMISSION development seeds 9957001 and 9957019 in
both positions against intact Arlene. Controls were read from retained records,
not rerun. Treatment and control both finish 2W/0T/2L. Every treatment adds 5 own
cash and 0 rival cash. Across 2,876 compared action/bank rows, only own market
slot 1 at decision 121 changes; every later authored action on both sides is
identical, and the +5 cash delta persists through terminal.

These are two mirrored development regimes, not four independent regimes, a
held panel, current canonical-package evidence, or a selected-policy promotion.
The experiment uses frozen SELL SHA-256 `32c8610c...`, not the later canonical
TITAN archive.

`RESULTS.json` is the compact result. `EVIDENCE.json` records exact source hashes,
the independent rerun, and the complete Library package identity. Consumers with
Library access can materialize file
`file_0000000011dc81fda369d6f7595dd75d`, which contains the full four treatment
traces, retained controls, telemetry, input closure, scripts, logs, and original
local delivery record.

## Reproduce the component suite

Use an existing Commons checkout and pinned engine cache:

```sh
cd revenue/kaggriculture/cloud-labor-capital/idle_hire
TITAN_REPO_ROOT=/path/to/commons \
TITAN_ENGINE_DIR=/path/to/pinned-engine \
python3 -B test_redundant_hire.py --report /tmp/redundant-hire-results.json
```

The test loader checks the official engine hashes through the existing
`cloud-eval/evaluate.py` road. No network or game panel is started by this command.

## Source boundaries

This component preserves DOCK's existing `cloud-labor-capital/` implementation,
its original evidence, and the cash-trough correction. It does not alter the
canonical TITAN runtime, build, feature configuration, current archive, or
checkpoint submission. The complete caller still owns future economic selection.

New source is Apache-2.0. Existing Arlene, frozen SELL, evaluator, and official
engine source remain under their original licenses and attribution. See
`NOTICE.md` and the retained package for the full dependency closure.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
