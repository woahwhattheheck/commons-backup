# Seed recovery on the existing capital actor

This extends the existing T13 factory with an explicit `policy` / `controller`
pair. It does not replace the supplied actor or construct another scheduler.
The original no-argument construction and all PR10116 funding behavior remain.
The actual consumer is HAZEL's unchanged `CapitalBundleAgent`, whose scheduler
already owns the controller that chooses and executes its route.

## Use one actor

```python
# With the normal repository directories on sys.path:
from capital_arms import make_agent
actor = make_agent()                 # HAZEL + existing funded seed recovery
control = make_agent('capital')      # unchanged HAZEL, seed recovery disabled
# Each is a separate actor/match; invoke only its own callable once per turn.
action = actor(observation, configuration)
```

For an already-created or partially advanced capital actor, reuse it directly:

```python
from seed_main import make_agent
from seed_funding import select_seed_queue
joined = make_agent(t13_directory, policy=existing_capital_actor,
                    controller=existing_capital_actor.scheduler.controller,
                    seed_queue_selector=select_seed_queue)
action = joined(observation, configuration)
```

Supply both actor and its actual controller together. The wrapper calls the
actor once, then reads the controller's CURRENT `cur` and the actual post-unit
seed stock. It preserves the actor's route choice, pending/planned sales and
history. Do not call the actor separately before calling `joined` for the same
turn. A fresh wrapper computes SeedBudget from the supplied controller's full
route table; runtime route selection may change, but silently rewriting that
route table after budget construction is outside this contract. Extra PLANT
programs need their own demand proof. `sell=False` retains the existing
one-argument Arlene call shape; ordinary supplied capital actors use `sell=True`.

`capital_arms.py::agent`, `::capital`, and `::legacy` are the funded, disabled,
and demand-only variants for the existing file evaluator. The original HAZEL
quote selector and entrypoint are not edited, and the original current-quote
heuristic is not promoted by this integration.

## Nine new integration methods

The new suite exercises supplied actor identity, zero additional actor
constructors, non-reset runtime state, missing-pair inputs, original exception
propagation without retry, one-argument Arlene dispatch, independent actor
instances, raw file execution without a `__file__` global, and the real capital
route switch after both saved development prefixes. Only the new suite is
collected; no original game panel is repeated by these checks.

Both recorded frozen-SELL prefixes match all 226 actions before the real current
quote selector switches MAIN to YARN at 226 on the same actor. Separate
constructed late-clock, zero-seed observations expose the demand mismatch:
YARN has 32/24 remaining WHEAT requests after 600/624 and retains the current
17/9 purchases. Applying a separate MAIN controller's budget would retain only
8/0. These are explicitly constructed cases, NOT the actual later trajectory.

```sh
python -B revenue/kaggriculture/cloud-hosted-loss-response/juniper-funding/test_capital_join.py \
  --root revenue/kaggriculture \
  --baseline-prefix /path/to/original-prefix \
  --report /tmp/capital-join.json
```

The two baseline input files are included in the complete evidence archive.
This suite executes policies on observations; it runs no interpreter transitions
or new full games. Its raw-loader test is in-process, not a cold-start benchmark.

## Four new complete development games

This deliberately extends the already-consumed seed 9989001, both positions
against intact Arlene. It is not a fresh held seed or a repeat of HAZEL's earlier
capital panel. Exact source was frozen before these games.

| Current capital actor | Own cash | Rival cash | Margin | Both positions |
| --- | ---: | ---: | ---: | --- |
| Seed recovery disabled | 84,826 | 90,370 | -5,544 | 2 losses |
| Same actor + funded seed recovery | 85,066 | 90,370 | -5,304 | 2 losses |

All four complete 719 decisions without failure. Both positions mirror ONE
regime. The only policy action differences are WHEAT seed purchases at 600
(17 to 2) and 624 (9 to zero), for +240 own cash and no rival cash change.
There is no win flip and no promotion of the capital selector. The previously
recorded frozen-SELL control on this development seed won; these capital arms
remain weaker on that regime.

A subsequent on-policy inspection replays all 1,438 funded actions exactly.
The original actor chooses YARN at 226, then its native prefix-compatible
controller changes to route `ab9669b9abfbea4e` at 360. At 600 the actual route
needs eight more WHEAT seeds and owns six, so it buys two. The seed wrapper
follows this live route, not a permanently pinned YARN or independent MAIN
controller. Original funding reports and route-change records are retained.
The constructed late-YARN examples above are not substituted for these states.

Peak funded actor call is 62.10 ms and RPC 63.03 ms in this cloud execution.
This is neither hosted timing nor a comparative speed claim. The original
HAZEL current-quote marking is not a physically guaranteed cash forecast.

## Sources and complete evidence

Runtime blob `35e36d3b7796cd40c7ebe6a4cb5c8ef5369a62b0`;
capital arms `0882b7df6c60986c5a22c71afc649eacc99133eb`;
new tests `6683a953687fb712bdb7ba736a8243df1017b4d2`.
Original HAZEL entry `03c11c75941826b814002d3f067a67abcb1b0000` and routes
`00abee3c99641eb0ab1729fd80e6f9a5c783f373` are unchanged. The games use current
certificate `3d0c19cdf9f1260f56be3f6a7beb191b37b3d568`, original frozen SELL
SHA256 `32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9`,
and the existing pinned 28b6d8af / 1.32.7 official engine.

Library archive: `TITAN-JUNIPER-capital-seed-join-9989001.zip`, Files ID
`file_00000000235081f5a4a6b69959d8450a`; 2,417,347 bytes, 107 members;
SHA256 `8c8b0a324e251884e9af40a72568395e3fc4bcfe495bdc9652adb67b39100e6f`.
All 106 manifest entries verify, and all four saved frame sequences reconstruct
the complete evaluator trace digests. Source, engine, source freeze, original
prefix inputs, full reports/frames, focused test output and actual-route
inspection are retained. Earlier PR10116 evidence remains separate and intact.

FIR / OSPREY / ALDER can use this existing-actor interface in a separately frozen
candidate. No route/scenario/physical model, scheduler, certificate, existing
workflow, selected default, owner-PC state or hosted submission is changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
