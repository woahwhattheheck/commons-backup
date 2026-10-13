# Terminal shed admission

Optional component for ATLAS/T08; the selected default is unchanged. It optimizes which goods enter a capacity-constrained shed on the final recorded action (`episodeSteps - 2`, normally 718). It takes the already-selected complete action and does not construct a second controller.

## Callable

```python
from market_primitives import make_primitives
from terminal_admission import optimize_terminal_admission

runtime = make_primitives(existing_sell_mechanics)
# The existing producer has already supplied selected_action exactly once.
action, report = optimize_terminal_admission(
    runtime, observation, configuration, selected_action, rival_scenarios,
    max_states=32, max_candidates=32, time_budget_s=0.15,
)
```

`RivalScenario(name, shed, market, provenance)` represents an explicit hypothesis about the rival's **post-worker** stock and complete SELL-only queue. No private rival inventory or actual rival action is an input. The supplied finite family has no implied probabilities and is not a claim to cover every feasible rival response. An empty family preserves the original action. `TerminalAdmissionAgent` is an optional convenience consumer that invokes the supplied producer exactly once and preserves a producer-body exception.

The runtime needs only `terminal_admission.py`, `market_primitives.py`, and the existing SELL `mechanics` module. The latter is not copied into this directory. The three additional market definitions are mechanically identical to the pinned official source and bind to that existing module without modifying it. A fresh `python -I -S` process executes the component without `kaggle_environments` or third-party packages. The full official interpreter is used only by validation/evaluation.

## Economic scope

Workers act in farmer-then-hands order; the market runs only after every worker. A prior market sale cannot free room for a later worker. DROP deletes overflow carry, PLACE retains the remainder, and PICKUP can clear low-value stored goods for a later higher-value deposit.

For shed-adjacent workers whose supplied action is storage-only, search offers complete PASS/DROP/PLACE/PICKUP sequences. Other work, movement, and animal placement remain unchanged. Existing market slot indices are retained; the first SELL for a product is sized to actual post-worker stock, later duplicate SELL quantities become zero, and missing products can append within the existing order limit. Active purchases, HIRE and land orders preserve the supplied action.

A candidate must strictly improve own-minus-rival proceeds against **both** the original complete action and the same-workers liquidation control in every supplied scenario. This prevents crediting admission for a change that is merely additional liquidation. Current quotes only rank/prune candidates; exact paired-market execution selects them.

All integer quantities are offered for lots up to 16 units. Larger lots use explicit capacity/arrival breakpoints. Beam pruning, quantity sampling, and cooperative-budget exhaustion are reported; none supports a global-optimum claim. The budget is not a hard RPC deadline: initialization or a market evaluation already in progress can overrun it. The parent producer's time and cold imports are separate.

A sufficient no-pressure fast path sums the current shed and all carried items, including inaccessible carry. When this bound fits, the original action is returned without search. This is intentionally a capacity-competition component, not a replacement for earlier terminal routing or general liquidation.

## Executed result

**23 test methods passed.** Nineteen recorded constructed scenario cases matched 57 complete official-interpreter transitions (original, liquidation control, selected). Additional coverage includes exhaustive independent action enumeration on 26 small constructed states, both player positions, partial clearance, fixed market slots, rival-sale reversal, exact source extraction, non-mutation, producer-call count and offline runtime composition.

A constructed capacity-3 case has WHEAT3 arriving before WOOL3. Original DROP ordering sells wheat for 73; preserving the room for wool sells for 600, a +527 margin gain in the idle-rival case. A full initial shed instead requires PICKUP before the later deposit. In a separate large-lot case, a rival's earlier full wool sale drives the later wool price down: the idle-only improvement is not selected once that rival-sale hypothesis is included.

**Natural development did not demonstrate an admission gain.** Seeds 9957001 and 9957019, both positions against intact Arlene and Apex, supplied eight complete games. The original, liquidation control and admission terminal continuations all remain 6W/0T/2L with identical cash. No final-turn storage-pressure case occurred. Mirrored results are not independent samples. The original full-game prefixes were reused exactly; these are not 24 independent full games.

The initial version spent 150–224 ms of its reported search-body time on these non-pressure states and exhausted its cooperative budget. The revised component returns unchanged through the no-pressure path. Retained whole-call measurements on the same eight final states are sub-millisecond; these exclude the producer, scenario construction and cold import. See `RESULTS.json` for measured values and all eight final scores.

Two initial first-seed Apex setup attempts failed because the local shared library had not been built. Those attempts remain in the full evidence. The existing C++ sources were then compiled with their include path, and only those two cells were completed. No new seed panel, held-set claim, leaderboard gain, default change, or Kaggle upload is included.

## Reproduce without more full games

Use the existing pinned engine cache and repository evaluator; no new export workflow is needed.

```bash
export TITAN_REPO_ROOT="$PWD"
export TITAN_ENGINE_DIR=/path/to/existing/pinned-engine
python -B revenue/kaggriculture/cloud-shed-admission/test_terminal_admission.py
python -B revenue/kaggriculture/cloud-shed-admission/replay_evidence.py \
  --repo-root "$PWD" --engine-dir "$TITAN_ENGINE_DIR" \
  --archive revenue/kaggriculture/cloud-shed-admission/reached-terminal-cases.json.xz.b64
```

The compact archive contains the eight exact captured terminal states, actual actions, prior final-bank values and original trace identities. The replay policy receives only its own observation; the evaluator alone consumes the actual rival state/action. `evaluate_terminal.py` composes the existing process-isolated runner for a separately assigned future full-game scope. Its seeds must be explicit. The tested original producer is frozen SELL `32c8610c`, not PR9997's integrated archive.

Complete prior action traces, all attempted-game reports, both runtime versions' evidence and exact source are retained in ChatGPT Library as `/titan_shed_admission_evidence_2026-09-07.zip`. The compact reached states and replay source are also in this directory, so ordinary consumption does not require retrieving that larger archive. Source hashes and archive identities are in `SOURCE.json`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
