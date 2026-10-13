# ARC-AGI-3 deterministic exploration baseline

Paid-work lane: ARC Prize 2026 / ARC-AGI-3. This directory is a reproducible, CPU-first baseline and submission-readiness package. It does **not** contain competition data, an ARC API key, a Kaggle submission, or a claimed leaderboard score.

## Pinned public contract

Verified 2026-09-08 against the organizer's current public material:

- Competition: ARC-AGI-3, interactive reasoning over novel turn-based game environments.
- Milestone 2: 2026-09-30 23:59 UTC. Final entry/team merger: 2026-10-26. Final submission: 2026-11-02 23:59 UTC.
- Guaranteed top-score pool: $75,000 ($40k/$15k/$10k/$5k/$5k); separate 100% grand prize is conditional.
- Frames: one or more 2-D grids, maximum 64x64, cell values 0..15.
- States: `NOT_PLAYED`, `NOT_FINISHED`, `WIN`, `GAME_OVER`.
- Actions: `RESET`, `ACTION1`..`ACTION7`; the frame's `available_actions` is authoritative. `ACTION6` requires integer `x,y` coordinates in 0..63.

Public references:

- https://arcprize.org/competitions/2026/arc-agi-3
- https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview
- https://github.com/arcprize/docs/blob/main/actions.mdx
- https://github.com/arcprize/docs/blob/main/create-agent.mdx
- https://github.com/arcprize/ARC-AGI-3-Agents

Exact upstream pins used here are in `environment.lock`.

## What this baseline does

`arc3_baseline.py` implements a deterministic model-based frontier explorer with no third-party dependencies and no network access. It validates the public frame/action contract, builds an online transition graph keyed by visual-state hashes, tries every legal state/action frontier once, rejects learned self-loops as navigation edges, and then routes through the shortest known transition path toward a visited state that still has an untried action. Novelty/progress UCB remains only a deterministic fallback when the learned graph has no reachable frontier. `ACTION6` coordinates are explored across changed regions, non-background connected components, and deterministic anchors.

The policy deliberately does not encode any private game solution or fixed public-game action sequence. It is a measurable floor to iterate from: every emitted action is legal under the observed action set, every transition is recorded, failed/no-change actions are remembered, repeated states can reuse learned paths to reach unexplored frontiers, and level completion receives a strong reward signal. The v2 frontier logic was implemented clean-room; no third-party solver source was copied.

`competition_agent.py` is the thin adapter for the official `arcprize/ARC-AGI-3-Agents` harness. `test_arc3_baseline.py` is an offline synthetic contract suite.

## Offline verification

From this directory:

```bash
python -m py_compile arc3_baseline.py competition_agent.py test_arc3_baseline.py
python test_arc3_baseline.py
```

The authored checkpoint was run with CPython and passed 13/13 tests. That is synthetic/offline evidence only; it is not an ARC score.

## Run in the official harness

Use a clean checkout of the pinned official agents repository, then copy the two agent files into `agents/`:

```bash
cp arc3_baseline.py /path/to/ARC-AGI-3-Agents/agents/arc3_baseline.py
cp competition_agent.py /path/to/ARC-AGI-3-Agents/agents/sol_arc3.py
```

Register `SolArc3` in the official `agents/__init__.py` / `AVAILABLE_AGENTS` mapping as described in the organizer's `create-agent.mdx`. Then, from the official checkout after its normal environment setup and with an owner-provided `ARC_API_KEY`:

```bash
uv run main.py --agent=solarc3 --game=ls20
```

The adapter uses only the official `FrameData`, `GameAction`, `GameState`, and `Agent` surfaces. `SOL_ARC3_MAX_ACTIONS` optionally changes the default 400-action ceiling.

## Next measured iterations

1. Run v2 against the organizer's public/local game set and record per-game score, action count, state coverage, frontier-route count, learned self-loops, and terminal failure state.
2. Add role-free object tracking so visually distinct but structurally equivalent movement states can share action-effect evidence.
3. Infer reversible movement/interact/coordinate effects from observed deltas, then plan over those effect hypotheses without level IDs or fixed coordinates.
4. Compare frontier routing against the frozen v1 novelty/UCB behavior on identical public game versions and action budgets.
5. Publish any actual score with game/version, environment commit, notebook version, and raw run receipt. Never infer a leaderboard score from synthetic tests.

## Data and submission boundary

No competition-only dataset is committed here. Do not upload restricted challenge material to hosted model APIs. Registration, rule acceptance, Kaggle execution, and final submission are separate authenticated account actions and are not claimed by this package.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

