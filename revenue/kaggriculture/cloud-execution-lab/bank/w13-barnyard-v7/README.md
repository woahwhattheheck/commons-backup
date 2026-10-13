# W13 reacting opponent bank — Barnyard Economist V7

This package makes Roman Rozen's already-preserved Barnyard Economist V7 directly callable from the TITAN frontier bank without changing one policy byte. It is an additional **research/diversity opponent**, not a promotion over Arlene/Apex and not a current-top-10 claim.

## Callable entry points

- `adapter.py::agent(observation, configuration=None)` — evaluator-compatible singleton for one actor process.
- `adapter.py::make_agent()` — preferred factory; returns a fresh wrapped policy instance for one actor/game.

The adapter hashes `upstream/main.py` before execution and refuses drift. The upstream policy only accepts `obs`, so the wrapper deliberately slices an optional evaluator `configuration` argument. It does not rewrite actions, route tables, state, timing or policy branches.

## Exact source and redistribution

Author: Roman Rozen (`romanrozen`). Public notebook: `strong-barnyard-economist`, scriptVersionId `341074820`, version 7. The normalized `main.py` is 27,244 bytes, SHA-256 `997e6bfc5234534e246e945bc61c87858ebf997ab85b0a5c9427dd4ed710f1b6`, copied here by same-repository Git blob identity from the reviewed T07 package.

Keep `upstream/LICENSE`, `upstream/NOTICE.md` and `upstream/SOURCE.json` with the policy. The source receipt records Apache-2.0 evidence from Kaggle's indexed exact-version page and explicitly preserves the limitation that the rendered pull metadata itself had no license field. Do not widen that claim or substitute another agent's notice.

Runtime binding: Python 3.10+ on Linux; the policy imports only Python standard-library modules. The preserved official-engine validation used `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

## Why this adds bank coverage

The legacy runnable six are Arlene, Apex, Kaito V43, COK V10, public Breaking-the-Tie V12 and the submitted V1. S11 separately added pass/random, Deepesh Farmbrain, two Lonespear entries and Amey V43/V16. Barnyard V7 is a different retained source hash and is absent from both sets.

This is real reacting code, not a replay tape. The published policy observes public farm/market state and contains premium-sale preemption/repayment, sell ranking, weed repair and terminal liquidation. Existing exact-source near-clone replay observed 15 preemptions and 15 repayments per game; disabling only the preemption flag changed actions and reduced cash in those diagnostic games.

## Validation boundary

The exact source bytes already have stronger pinned-engine evidence than a one-game smoke: 32 primary games across development and held panels, both seats, 719 decisions per game, zero Barnyard runtime failures, under official engine commit `28b6d8af…`. Barnyard lost all 16 primary candidate-vs-Arlene/Apex games, so this package is deliberately tagged `research_diversity` and makes no superiority claim.

W13 did **not** execute a new official-engine match in this cloud VM because the pinned engine package is not present. The manifest records that limitation rather than relabeling old games as new. W13 does add a focused callable regression using the preserved real step-0 observation plus source-hash enforcement. Run it from this directory with:

```sh
python -m unittest -v test_adapter.py
```

No TITAN strategy, current pointer, archive, replay, hosted submission, provider state, spending or owner-PC state is modified by this bank package.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
