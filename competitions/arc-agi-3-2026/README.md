# ARC-AGI-3 SAGE — State-Action Generalization Engine

Operation: `ARC3-SAGE-WORLDMODEL-SKILL-ENGINE-ZKDP3F7-20260913`  
Owner: Z-KolmogorovDelta-120612-P3F7 (`ZKD-P3F7`) / GPT-5.6 Sol  
Tracking: Commons #14065

SAGE is a dependency-free research substrate for the 2026 ARC-AGI-3 interactive-agent competition. It is intentionally **not** a hard-coded solver for public games. The engine treats action meanings as latent, retains every frame returned by an action, learns state/action/effect evidence, spends action budget on information-rich experiments, and promotes successful traces into replayable skills only behind generalized precondition gates.

## Why this lane matters

ARC-AGI-3 is interactive. A solver is scored on completing hidden, human-solvable games efficiently rather than producing a static output grid. The official toolkit exposes a game-specific action space that may change after each step, and complex actions may require `(x,y)` coordinates. API responses may contain several frames when the environment internally animates before settling. SAGE therefore treats an episode as an evidence stream:

`all frames -> scene abstraction -> action -> temporal effect -> hypothesis update -> skill evidence`

Discarding intermediate animation frames or assuming `ACTION1 == UP` is a research error, not a harmless convenience.

## Shipped components

- `sage.py`
  - exact grid/type/bounds contract;
  - connected-component scene abstraction;
  - animation-aware effect signatures;
  - state/action effect statistics and entropy;
  - action-efficient exploration/model-guided policy;
  - coordinate candidate reduction for complex actions;
  - successful-trace -> skill induction;
  - precondition/confidence-gated skill replay;
  - explicit opt-in consumer of the public symbolic planner.
- `mock_env.py`
  - no-network hidden-control game;
  - action semantics are scrambled per seed;
  - switch/door puzzle emits a real three-frame door animation;
  - complex click action path.
- `adapter.py`
  - structural adapter for official `arc_agi`/`arcengine` objects;
  - retains all frames;
  - re-reads the environment's current `action_space` every step;
  - imports without toolkit/network/API keys.
- `receipts.py`
  - canonical deterministic trace/evidence receipts;
  - exact trace/effect/frame digests;
  - fixed-false competition/submission/revenue authority.
- `benchmark.py`
  - deterministic no-network seed sweep.
- `test_sage.py`
  - retained historical checks; not a requirement to run or extend a suite.

## Opt-in symbolic lookahead

`SAGEAgent()` preserves the existing policy and does not import the optional planner. To use the landed public planner through the actual agent:

```python
from sage import SAGEAgent
from sage_symbolic_planner import PlannerBudget

agent = SAGEAgent(
    symbolic_lookahead=True,
    planner_budget=PlannerBudget(
        max_depth=3, max_width=6, max_nodes=18, max_plan_actions=3,
    ),
)
decision = agent.decide(observation, actions_left=remaining_real_actions)
# Execute only decision.action in the environment, then retain its actual response.
agent.learn(observation, decision, next_observation)
```

The budget defaults, when omitted in enabled mode, are depth 4, width 6, 96 simulated nodes and at most 8 proposed actions. Planning also receives the caller's exact remaining real-action ceiling; its depth cannot exceed that ceiling. The node cap bounds simulated expansions, not the cost of indexing the retained transition history. Planning itself never calls the environment. `actions_left` in enabled mode must be an exact integer in `[1, 1000000]`; a custom budget requires `symbolic_lookahead=True` and must pass the public `PlannerBudget` validation.

Each decision builds a fresh public `SageEvidenceAdapter` over the existing `WorldModel.transitions`. It uses the policy's current coordinate/action candidates for each concrete observation and stops candidate generation at terminal or inactive observations, even when they retain action names. A selected first action must be in the current candidate set and have a unanimous, exact, concrete predecessor/action outcome under the full-animation identity. An abstract, contradictory, losing or exact self-loop first step falls back to the unchanged skill/spatial/exploration policy. A new agent with no transitions also uses that policy. A terminal/inactive root or empty action space raises a clear `ValueError`; malformed evidence and programming errors are not silently swallowed. The current schema and standalone terminal boundary are documented in [SYMBOLIC_PLANNER.md](SYMBOLIC_PLANNER.md).

An accepted planner decision keeps the public `Decision` shape and uses mode `SYMBOLIC_LOOKAHEAD`. Its numeric evidence includes simulated nodes, proposed prefix length, the remaining real-action ceiling, and the planner's historical confidence/risk basis points. Those metrics are not calibrated win probabilities. `agent.last_plan` exposes the public plan for the current accepted decision only: it is `None` after fallback, the next decision starts afresh, and learning or resetting clears it. **Never execute `last_plan.selected_prefix` as a queued script.** A later suffix may end at an uncertain evidence boundary; observe the first action's actual response and replan.

`reset_episode(preserve_knowledge=True)` retains the existing model and skills, not a predicted plan. Preserve knowledge only across episodes with the same action semantics. Use `preserve_knowledge=False` when changing games or control mappings; that rebuilds model, skills and policy while retaining the opt-in configuration and budget. Matching pixels alone do not establish cross-game equivalence.

## One offline usage example

From `competitions/arc-agi-3-2026`, this uses the existing no-network environment to observe five simple probes, then makes and executes one planner-backed decision after a knowledge-preserving reset. It creates no test file, fixture archive or execution transcript.

```bash
python -B - <<'PY'
import json
from sage import SAGEAgent, ActionToken, Decision
from sage_symbolic_planner import PlannerBudget
from mock_env import SwitchDoorEnv

agent = SAGEAgent(symbolic_lookahead=True, planner_budget=PlannerBudget(
    max_depth=3, max_width=6, max_nodes=18, max_plan_actions=3,
))
env = SwitchDoorEnv(seed=0)
for name in ('ACTION1', 'ACTION2', 'ACTION3', 'ACTION4', 'ACTION5'):
    before = env.reset()
    token = ActionToken(name)
    after = env.step(token)
    agent.learn(before, Decision(token, 'OFFLINE_PROBE', 0.0, ()), after)
agent.reset_episode(preserve_knowledge=True)
before = env.reset()
decision = agent.decide(before, actions_left=2)
planned = agent.last_plan
if planned is None:
    raise SystemExit(f'No symbolic decision on the retained input: {decision.mode}')
after = env.step(decision.action)
transition = agent.learn(before, decision, after)
print(json.dumps({
    'mode': decision.mode,
    'first_action': decision.action.key,
    'planner_schema': planned.receipt['schema'],
    'selected_prefix': list(planned.selected_prefix),
    'simulated_nodes': planned.simulated_nodes,
    'node_ceiling': 18,
    'real_action_ceiling': planned.receipt['real_action_ceiling'],
    'simulation_environment_actions': planned.receipt['real_actions_spent_by_simulation'],
    'executed_environment_actions_after_reset': env.actions,
    'changed_cells': transition.effect.changed_count,
    'state': after.state,
    'last_plan_cleared_after_learning': agent.last_plan is None,
    'observed_transitions': len(agent.model.transitions),
}, sort_keys=True))
PY
```

This is an offline integration example, not a Kaggle/public-game/private-game score, a proof of improved play, or a reason to run a seed sweep. The existing default policy, planner scoring and original transition semantics are unchanged.

## Official-toolkit integration

The project does not acquire an ARC API key or create an ARC scorecard. A caller who already has an authorized official environment can pass it to:

```python
from adapter import run_official_episode
from sage import SAGEAgent

agent = SAGEAgent()
history = run_official_episode(env, agent, max_actions=80)
```

`run_official_episode()` re-acquires `env.action_space` after each action. The adapter translates SAGE `ActionToken`s to `arcengine.GameAction` only at execution time. The opt-in agent above can be passed to the same adapter without changing this call contract.

## Research roadmap to Milestone 2

1. **Public-game trace corpus** — collect exact, licensed/open traces from the official toolkit; preserve full animation arrays, action-space changes, terminal state, and reasoning metadata. Never store API keys.
2. **Effect factorization** — split state deltas into object motion, spawn/despawn, recolor, topology, counters/UI and camera/animation effects. Use causal probes instead of relying on one opaque digest.
3. **Action semantics induction** — infer per-game action roles with counterfactual/probe pairs and confidence intervals. Explicitly model dead/no-op actions because they may still consume budget.
4. **Skill parameterization** — move from exact action suffixes to object/target-relative programs (`move-to(component)`, `toggle(adjacent)`, `click(candidate)`) with precondition/effect contracts.
5. **Planning** — the bounded symbolic planner now has an opt-in SAGE consumer; measure useful decision changes before making any performance or default-promotion claim.
6. **Cross-level transfer** — retain skill families only where generalized scene/effect evidence survives a changed level; fail closed on mismatched action spaces or state abstractions.
7. **Notebook profile** — deterministic cache discipline, zero internet, bounded memory, and wall-clock instrumentation for Kaggle <=9h requirements.

## Evaluation contract

Every experiment should report at least:

- exact agent revision;
- toolkit/package revision;
- game IDs / public-vs-mock classification;
- seed and action budget;
- win/levels completed;
- real actions used;
- number of no-effect actions;
- number of animation-bearing responses;
- learned/replayed skill counts;
- trace receipt SHA-256;
- runtime and hardware class.

Do not aggregate incomparable agent revisions or toolkit/game generations as if they were one experiment.

## Authority boundary

This carrier does **not** accept Kaggle/ARC rules, join a team, open a paid API account, use owner hardware, spend cloud/GPU credits, upload a notebook, submit to the competition, or claim a leaderboard score, prize, payment, cash, or revenue. Those are separate authenticated external actions.
