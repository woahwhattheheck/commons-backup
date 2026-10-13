# SAGE bounded symbolic planner

This additive layer performs deterministic bounded lookahead over evidence already held by SAGE. It is **recommendation evidence only**: it does not call an ARC environment, spend a real action, accept rules, submit to Kaggle, or claim leaderboard/prize state.

## Evidence boundary

`SageEvidenceAdapter` binds every retained animation frame **in order**, the normalized available action set, terminal/progress metadata, and the complete SAGE transition evidence set into content digests. Different temporal histories do not become the same predecessor merely because their final frames match. Generic observations that expose only `frame` are treated as a one-frame sequence; a supplied `frames` sequence must be nonempty and end at `frame`.

Candidate effects are selected in this order: exact observed predecessor plus the full action token (including coordinates), semantics-free scene class plus action name, global action evidence, then `UNOBSERVED`.

A concrete successor, terminal state, level progress, or successor-derived novelty is eligible for deeper search only when **all exact predecessor/action observations** agree on the successor digest, progress and terminal semantics. Agreement inside the modal effect alone is insufficient: two recorded wins and one conflicting outcome remain uncertain, not a deterministic win.

SCENE/GLOBAL evidence can still inform effect, confidence and risk scoring, but cannot supply another predecessor's concrete future. Disagreement or absent successor evidence produces an **abstract effect state** with no inferred future action space. Lookahead stops there; the planner does not fabricate pixels or additional actions. An unobserved root action can still be recommended as exploration, not as a known outcome. Unanimous exact multi-step paths remain eligible.

**Only `NOT_FINISHED` states may expand.** The public `plan()` snapshots its adapter's root and rejects a terminal or inactive root with `ValueError("planner requires a NOT_FINISHED root state")`. During search, neither SAGE nor a generic adapter is asked to generate actions or simulate from a `GAME_OVER`, `WIN`, `NOT_PLAYED`, or other non-active state. SAGE's evidence adapter independently returns no hypotheses when either the symbolic state or resolved observation is terminal/inactive, even if action names are still advertised. A path may end at a terminal outcome; it cannot manufacture a continuation beyond that outcome. This does not change how terminal outcomes themselves are scored.

## Search contract

The search is deterministic bounded best-first lookahead. Its hard controls are `max_depth`, `max_width`, `max_nodes`, `max_plan_actions`, and the independently supplied `actions_left` real-action ceiling. Every simulated expansion increments `simulated_nodes`; simulation always records `real_actions_spent_by_simulation = 0`.

Scoring exposes explicit terminal-WIN, progress, novelty, confidence, uncertainty, changed-effect, risk, loop, and depth terms. Transpositions keep the best score seen for a symbolic state; loops are penalized and never recursively expanded. Tie-breaking is stable and lexical only after semantic score dimensions tie. The active-state wrapper delegates to the same search/evidence implementation; it is not a new search engine or transition store.

For the actual agent consumer, use `SAGEAgent(symbolic_lookahead=True, planner_budget=PlannerBudget(...))` as documented in the [agent README](README.md). The default agent policy remains unchanged. Execute only the chosen first action, observe its actual response, learn and decide again rather than replaying a predicted suffix.

## Receipt and verification

The public schema is `commons.arc3-sage-symbolic-planner/v4`, planner version `4`. Reachability policy `exact-predecessor-full-animation-unanimous-active-state-reachability/v4` binds the terminal boundary as well as the existing unanimous temporal-evidence rules. Every decision emits canonical JSON binding:

- root state digest, complete model-evidence digest, observation identity and reachability policies;
- deterministic root candidate order;
- exact search budget and scoring weights;
- simulated node count;
- selected action prefix, score, progress, confidence and risk;
- real-action authorization ceiling and planned real-action count;
- fixed-false external-action authority flags;
- SHA-256 of the complete unsealed receipt.

The SAGE policies are bound through the state/model digests, not extra top-level receipt fields; the public schema/version also identifies the active-state rule for generic adapters. `verify_receipt()` first checks the receipt field set, digest and schema/version, then recomputes the plan from the supplied current adapter, budget, weights and real-action ceiling. Model drift, state drift, budget/policy drift, candidate-order changes and receipt tampering fail closed. Historical v1, final-frame-only v2, and pre-terminal-boundary v3 receipts are not accepted as v4. Regenerate from current evidence rather than relabeling an old receipt.

## Historical benchmark and provenance

Historical `planner_benchmark.py` material compares a deliberately local one-step progress preference with bounded lookahead across deterministic two-step terminal fixtures. It demonstrates wiring only; it is **not** a public/private ARC benchmark, hidden-task estimate, or leaderboard claim. The private `_sage_symbolic_planner_core.py` remains unchanged; callers should use the public `sage_symbolic_planner` module.

The September 23 v3 recovery ran only the retained `test_modal_exact_win_cannot_determinize_conflicting_exact_outcome` method with its synthetic fixtures and blob-matched public facade/private core. That earlier recovery did not establish real-game performance. Its additional regression/benchmark material remains in PR #15631 history at `9d94a9eadd3734f86753709b954e7a38385157f9`.

The later agent integration in #19297 ran one actual offline usage example with v3, not an official game or a suite. The v4 terminal-boundary follow-up is a source-level repair; it adds no test files, benchmark files, workflows or stored execution transcripts, and does not claim another execution. Neither historical run is a reason to rerun a suite.

Original planner and correction authorship remains with the contributors recorded in PR #15631, including Z-Sable, ZFA-V5K2/ZGC-R5M8, Z-Sol-1447 and the retained recovery contributors. The terminal-boundary repair preserves the historical core bytes and extends the public facade.
