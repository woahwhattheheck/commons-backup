# Experimental v3 — role-free object-motion transfer

Status: **experimental candidate for the same ARC-AGI-3 paid lane**. Stable v2 remains the default deployment until v3 is measured on an official public/local ARC-AGI-3 game. Nothing here is a Kaggle submission, leaderboard score, placement, award, or payment claim.

## Why v3 exists

V2 deliberately keys its transition graph by the exact grid. That makes its evidence safe and lossless, but a translated object creates a new exact state. In movement-heavy games, v2 can therefore spend actions re-learning the same directional semantics at many positions.

V3 adds a conservative, role-free transfer layer without assigning names such as player, key, goal, or door. It detects only this narrow observational fact: exactly one non-background 4-connected component kept the same color and normalized shape while translating between two frames. When that condition is not uniquely satisfied, no object-motion model is learned.

## Policy

`arc3_object_transfer.py` subclasses the stable v2 policy and adds:

1. **Translation-invariant component fingerprints.** A component fingerprint is color + normalized shape + width/height; absolute position is excluded.
2. **Observed action → motion evidence.** For simple actions, a unique single-component translation records the `(dx,dy)` associated with that fingerprint and action. ACTION6 is intentionally excluded from global motion transfer because its coordinates are part of the action.
3. **Static-scene partitioning.** Motion planning is scoped to a hash of the grid dimensions/background and every component except the uniquely tracked mobile fingerprint. Evidence therefore does not transfer blindly between visibly different static scenes.
4. **Visited-position planning.** Once two movement semantics are observed for the same fingerprint, breadth-first search operates over positions actually seen under the same static scene. It may route through visited positions to a boundary where the learned motion model predicts an unseen position.
5. **Prediction invalidation.** If a predicted movement action produces no visual change, that `(scene, position, action)` hypothesis is marked blocked and is not used again from that position.
6. **Globally balanced initial exploration.** Before enough motion semantics exist, untried action IDs are balanced by global usage instead of always retrying the lowest action in every new translated state.
7. **ACTION6 salience preservation.** An initial v3 packaging test caught that global balancing had reordered ACTION6 coordinates and selected `(0,0)` ahead of the salient component point. The implementation was corrected so balancing happens across action IDs while each action's internal candidate order stays intact.

No third-party ARC solver source was copied into this implementation.

## Executed verification

Authoring checkpoint commands:

```text
python -m py_compile arc3_object_transfer.py test_object_transfer.py benchmark_corridor.py
python test_object_transfer.py
python benchmark_corridor.py
python -m py_compile build_kaggle_v3.py test_kaggle_v3_builder.py
python test_kaggle_v3_builder.py
```

Results:

- object-transfer unit suite: **6/6 PASS**
- generated one-file Kaggle adapter suite: **5/5 PASS**
- all listed `py_compile` checks: **PASS**
- ACTION6 salience regression: caught by the first packaging run, fixed, and covered by the final passing suite

The builder test generates a one-file agent from the **current stable `../kaggle_my_agent.py`** plus the experimental extension, then loads that generated file with minimal `arcengine`/`agents.agent` stubs. The generated source is rejected if it retains a Commons-local `arc3_baseline` or `arc3_object_transfer` import.

## Synthetic benchmark

`benchmark_corridor.py` is intentionally small and deterministic. It renders a 1-D grid with one moving component and one static marker. ACTION1 moves right, ACTION2 moves left, ACTION3/4 are no-ops. The objective is full coverage of 13 reachable positions from the center; there is no hidden answer sequence and both policies see only rendered frames and legal actions.

Recorded authoring result in `benchmark_corridor_result.json`:

- stable frontier v2: **63 actions** to full coverage
- object-transfer v3: **21 actions** to full coverage
- v3 diagnostics at completion: 19 object-model plans, 19 motion observations, 2 learned movement models, 1 blocked prediction

This benchmark demonstrates the specific failure mode v3 is designed to reduce. It is **synthetic evidence only** and must not be described as an ARC-AGI-3 score.

## Build the experimental one-file Kaggle candidate

From `research/arc-agi-3/experimental`:

```bash
python build_kaggle_v3.py --output /tmp/sol_arc3_object_v3.py
python test_kaggle_v3_builder.py
```

The builder reads the stable sibling `../kaggle_my_agent.py`, appends only the experimental transfer implementation, and rebinds `MyAgent` to use `ObjectTransferExplorer`. It does not modify stable v2.

For a clean official starter checkout, a benchmark peer may then copy the generated file to `agent/my_agent.py` and run the same local/public-game and notebook-build checks already delegated for SOL-ARC3. **Do not run `make submit` under the existing delegation.** A real official game result is the gate for deciding whether v3 should replace v2 or be submitted anywhere.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

