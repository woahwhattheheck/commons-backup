# ARC-AGI-3 Kaggle deployment readiness

This note closes the deployment gap between the generic ARC-AGI-3 research harness adapter and the organizer's current official Kaggle starter.

## Pinned starter contract

Observed 2026-09-08 from `arcprize/ARC-AGI-3-Kaggle-Starter`:

- starter main commit: `eeb1535404f321d280a8f9194bbc1d7aca5f05fc`
- `agent/my_agent.py` blob: `ae583247bd1bf7f238097ba07b67fa84fe3f8d13`
- `README.md` blob: `73e58bc5d45ad3623a2edea6931bf68ab6ceb393`
- `scripts/build_notebook.py` blob: `e5c13e87fac5f6a3acfe2d9a32bf621a16407e16`
- `scripts/play_local.py` blob: `6e11153821c5716f64971fba853351ec64636080`

The starter's contract is intentionally narrow: `agent/my_agent.py` must define `MyAgent(Agent)` with `is_done(...)` and `choose_action(...)`. `scripts/build_notebook.py` reads that one file and writes it into `/tmp/my_agent.py` inside the generated offline notebook before copying it into `agents/templates/my_agent.py` during the competition rerun. Because only one agent source file is spliced, a Kaggle-ready strategy must not depend on another local source file that the builder does not package.

## Drop-in file

`kaggle_my_agent.py` is the self-contained deployment form of the SOL-ARC3 deterministic frontier-model v2 baseline. To use it in a clean checkout of the pinned starter:

```bash
cp /path/to/commons/research/arc-agi-3/kaggle_my_agent.py agent/my_agent.py
make play-local GAME=ls20
make notebook
```

The file uses only Python's standard library plus `arcengine` and `agents.agent`, which the official framework provides. It obeys the current `available_actions` set, emits RESET for NOT_PLAYED/GAME_OVER, bounds ACTION6 coordinates to 0..63, and keeps exploration deterministic for a repeated observation sequence.

`make play-local` may need network access on the first run to download public game source into the starter cache. Once downloaded, the organizer says the game environments are cached for offline use.

## Authenticated boundary

`make submit` is an account action: it needs a Kaggle account with competition rules accepted, a project-local Kaggle access token, and a real Kaggle username in `notebooks/kernel-metadata.json`. The starter says `make submit` uploads/runs the notebook, but the entrant must subsequently open the completed kernel and deliberately choose **Submit to Competition** with `submission.parquet`; that second phase is what produces a leaderboard score. The starter currently documents a five-submission-per-day limit.

No `make submit`, competition rerun, leaderboard score, rank, prize, or payment is claimed by this Commons package.

## Offline verification

Run from this directory:

```bash
python -m py_compile kaggle_my_agent.py test_kaggle_my_agent_contract.py
python test_kaggle_my_agent_contract.py
```

The contract test injects minimal `arcengine`/`agents.agent` stubs so the single-file deployment can be tested without installing the competition package. It verifies the required `MyAgent` class, absence of an import back to the Commons research core, RESET behavior, integer `available_actions`, currently-legal action selection, ACTION6 data/bounds, stacked-frame normalization, invalid-color rejection, deterministic replay, shortest learned frontier routing, and structured reasoning.

## v2 exploration policy

The drop-in now uses the same clean-room deterministic frontier model as `arc3_baseline.py`: untried legal state/action pairs first; shortest learned non-self-loop route to a reachable unexplored state second; novelty/progress UCB only as fallback. The default action ceiling is 400 (`SOL_ARC3_MAX_ACTIONS` can override it). This is still a generic baseline, not a stored `ls20` answer sequence.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

