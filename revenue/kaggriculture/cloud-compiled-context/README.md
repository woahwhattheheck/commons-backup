# KAG-COMPILED-CONTEXT

A small offline strategic context and persistent installation controller over the
exact selected `dispatch_balanced` baseline. The default `candidate.py` preserves
baseline economics and prefers committed installation targets through DIG → BUILD
→ PLACE. It completes jobs from observed installed animals and replans invalid
live targets. Economic acquisition restrictions remain an explicitly experimental,
disabled arm after losing comparisons; they are not part of the default behavior.

**Do not replace the selected TITAN submission with this experiment.** Across 32 new
cloud games there were zero execution failures. The frozen default archive won 2/2
against lean20, won 0/2 against dispatch_balanced and 0/4 against Kaito/Igor (win counts).
Nine targeted contract tests pass. [RESULTS.md](RESULTS.md) has every final cash,
source/version/seat, runtime and retained null result. No hosted Kaggle result.

The default agent is 36,970 bytes, standard-library Python, with no LM, network,
hidden seed/future shops or public replay action sequence. The actual archive in
`export/submission.tar.gz` is 18,187 bytes including license grants and a manifest.
This is ordinary CPU code, not compression of a 3.66 GB model. [SOURCES.md](SOURCES.md)
records exactly which pinned LDA sources were read and separates source mechanisms,
this new design, code ancestry and measured results. Claude's live-model lane remains
separate and root owns its UI.

## Narrow interface for FLORA

| Function | Result and responsibility |
|---|---|
| `select_context(obs, configuration=None)` | Own cash, shed+carried stock, feed, workers, vacant capacity, inclusive remaining actions, crop/animal first-production bounds and return distance. |
| `advance(obs, configuration=None, previous=None, options=None)` | Persistent JSON daily plan: fixed targets, phase/reserves, backlog, observed outcomes, completion/expiry, installation intents, at most 8 feedback/bank entries. |
| `installation_jobs(obs, previous=None)` | `(jobs, outcomes)` for own carried livestock. Each job exposes worker, animal, target, next_operation, distance+operation metric and stale count. Compatible live tile and carried stock are required. |
| `situation_packet(context, state)` | Up to 2 situation-matched own advancing completed-plan examples immediately before live state. Local asset progress is not demonstrated terminal profit. |
| `constrain_orders(action, context, state)` | Experimental `(action, state)` market restriction arm. Disabled in default; not suitable for direct use with FLORA's land/crop policy. |

FLORA owns production scheduling; its files are unchanged. It can consume the
intents with its own priorities and pass its own caps/cost estimates to `advance`.
ROWAN owns detailed production timing/deadlines. The exposed first-production
horizons are conditional feasibility bounds, not a yield or cash forecast.

The daily plan completes only when actual installed/crop targets are reached and
livestock backlog clears. It may subsequently lose crops/animals; a historical
completion is not a continuing success guarantee. Next day, unmet plans expire and
replan from actual stock. Nominal targets can be unaffordable: expiry and measured
cash expose that failure. In the default arm, daily economic targets/reserves are
reported context; baseline purchase economics remain authoritative. Only persistent
installation target preferences affect actions. The planner never credits issued
BUY/BUILD commands as completed assets.

State resets on seat change or decreasing step, and same-step calls are idempotent.
Callers must reset explicitly for a new game with an indistinguishable initial step.
Worker identities last one day: `advance` resets installation intents at EOD; direct
`installation_jobs` callers must do the same. Memory is process-local, with no disk
writes. The development diagnostic wrapper is separate and excluded from exports.

## Build and use

```bash
python -B revenue/kaggriculture/cloud-compiled-context/test_controller.py
python -B revenue/kaggriculture/cloud-compiled-context/build.py
```

`build.py` enforces the exact dispatch_balanced hash and defines `agent` last for the
official loader. Its `build(output, control_orders=False)` API keeps the losing
restriction arm off by default. Explicit `control_orders=True` enables research
comparisons only. `pack-profile.json` works with the existing cloud-pack/pack.py;
see that builder's CLI. Use cloud-eval/evaluate.py with the exact pinned engine cache.

Owner-authored code is MIT OR CC-BY-4.0; both full grants accompany the export.
Copyright 2026 Bryce Xavier Muhlnickel / TokenJunkieLabs. Baseline authorship remains
Euler / ASTRA-WORK / ROWAN / SORREL / FLORA. Third-party source retains its license.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
