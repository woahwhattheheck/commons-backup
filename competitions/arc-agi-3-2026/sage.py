"""Public SAGE API assembled from dependency-free research modules."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sage_core import *  # re-export stable research primitives
from sage_model import EffectStats, ScenePrecondition, Skill, SkillLibrary, WorldModel
from sage_policy import Decision, Policy

if TYPE_CHECKING:
    from sage_symbolic_planner import PlanDecision, PlannerBudget


class SAGEAgent:
    """Stateful agent with optional, evidence-bounded symbolic lookahead."""

    def __init__(
        self,
        *,
        symbolic_lookahead: bool = False,
        planner_budget: PlannerBudget | None = None,
    ) -> None:
        if type(symbolic_lookahead) is not bool:
            raise ValueError("symbolic_lookahead must be a bool")
        if planner_budget is not None and not symbolic_lookahead:
            raise ValueError("planner_budget requires symbolic_lookahead=True")
        # Keep the default policy independent of the optional planner import.
        if symbolic_lookahead:
            from sage_symbolic_planner import PlannerBudget

            if planner_budget is None:
                planner_budget = PlannerBudget()
            if not isinstance(planner_budget, PlannerBudget):
                raise TypeError("planner_budget must be a public PlannerBudget")
            planner_budget.validate()
        self.symbolic_lookahead = symbolic_lookahead
        self.planner_budget = planner_budget
        self.last_plan: PlanDecision | None = None
        self.model = WorldModel()
        self.skills = SkillLibrary()
        self.policy = Policy(self.model, self.skills)
        self.trace: list[Transition] = []

    @staticmethod
    def _planning_candidates(obs: Observation) -> tuple[ActionToken, ...]:
        # A retained terminal observation may still advertise action names.
        # Neither WIN nor GAME_OVER (nor an unstarted state) permits a suffix.
        if obs.state != "NOT_FINISHED":
            return ()
        return Policy.candidate_actions(obs)

    def decide(self, obs: Observation, *, actions_left: int) -> Decision:
        self.last_plan = None
        if not self.symbolic_lookahead:
            return self.policy.choose(obs, actions_left=actions_left)
        if type(actions_left) is not int or not 1 <= actions_left <= 1_000_000:
            raise ValueError("actions_left must be an exact int in [1,1000000]")
        if obs.state != "NOT_FINISHED":
            raise ValueError("symbolic lookahead requires a NOT_FINISHED observation")
        candidates = self._planning_candidates(obs)
        if not candidates:
            raise ValueError("no available actions")
        if not self.model.transitions:
            return self.policy.choose(obs, actions_left=actions_left)

        from sage_symbolic_planner import SageEvidenceAdapter, plan

        # Rebuild from current observations and the existing model, never a
        # cached predicted suffix or a second transition store.
        adapter = SageEvidenceAdapter(
            self.model, obs, candidate_factory=self._planning_candidates
        )
        root = adapter.root_state()
        root_hypotheses = adapter.hypotheses(root)
        if not root_hypotheses:
            return self.policy.choose(obs, actions_left=actions_left)
        planned = plan(adapter, actions_left=actions_left, budget=self.planner_budget)
        action = planned.first_action
        if not isinstance(action, ActionToken) or action not in candidates:
            raise RuntimeError("symbolic planner returned a non-current action")
        first = next((h for h in root_hypotheses if h.action_key == action.key), None)
        if first is None:
            raise RuntimeError("symbolic planner lost its first-action evidence")
        # Public v3 only grants concrete reachability to unanimous exact
        # predecessor/action evidence. Abstract, conflicting, and losing first
        # steps defer to the unchanged skill/spatial/exploration policy.
        if (
            first.evidence_scope != "EXACT"
            or first.successor_observation is None
            or first.terminal not in {"NOT_FINISHED", "WIN"}
            or first.successor_observation_digest == root.digest
        ):
            return self.policy.choose(obs, actions_left=actions_left)
        self.last_plan = planned
        return Decision(
            action,
            "SYMBOLIC_LOOKAHEAD",
            float(planned.receipt["selected_score"]),
            (
                ("simulated_nodes", float(planned.simulated_nodes)),
                ("planned_real_actions", float(len(planned.selected_prefix))),
                ("real_action_ceiling", float(actions_left)),
                ("confidence_bps", float(planned.receipt["confidence_bps"])),
                ("risk_bps", float(planned.receipt["risk_bps"])),
            ),
        )

    def learn(self, before: Observation, decision: Decision, after: Observation) -> Transition:
        self.last_plan = None
        transition = Transition.build(before, decision.action, after)
        self.model.observe(transition)
        self.policy.record_transition(transition)
        self.trace.append(transition)
        if transition.effect.level_delta > 0 or after.state == "WIN":
            self.skills.learn_success_suffix(self.trace)
        return transition

    def reset_episode(self, *, preserve_knowledge: bool = True) -> None:
        self.last_plan = None
        self.trace.clear()
        self.policy._last_actions.clear()
        if not preserve_knowledge:
            self.model = WorldModel()
            self.skills = SkillLibrary()
            self.policy = Policy(self.model, self.skills)
