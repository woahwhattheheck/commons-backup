# SPDX-License-Identifier: Apache-2.0
"""Complete SELL-state adapter for the existing RILL/T04 route evaluator.

No simulator, route generator, actor reset, sale optimizer or live selection is
implemented here. Caller-supplied scenarios retain the original T04 meaning.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping, Sequence


class SellRouteView:
    """Expose the Arlene route seam while calling the WHOLE supplied SELL actor.

    RILL forks this facade before changing its route or calling its action. A
    deep copy therefore includes controller caches and SELL pending/planned/
    observation state, not just an Arlene clone. The pinned frozen scheduler
    has only copyable instance state; other actor families can supply a fork.
    """
    def __init__(self, scheduler: Any, configuration: Mapping[str, Any]):
        self.scheduler = scheduler
        self.configuration = deepcopy(dict(configuration))

    @property
    def cur(self):
        return self.scheduler.controller.cur

    @cur.setter
    def cur(self, route_id):
        self.scheduler.controller.cur = route_id

    @property
    def R(self):
        return self.scheduler.controller.R

    def _switch_ok(self, route_id, step):
        return self.scheduler.controller._switch_ok(route_id, step)

    def act(self, observation):
        return self.scheduler.act(observation, self.configuration)


def evaluate_sell_tails(scheduler: Any, route_ids: Sequence[str],
                        observation: Mapping[str, Any],
                        configuration: Mapping[str, Any], engine: Any, *,
                        replay_routes: Callable[..., dict],
                        simulate_bundle: Callable[..., dict],
                        scenarios: Mapping[str, Any], end_step: int,
                        limits: Any, fork_scheduler: Callable[[Any], Any] = deepcopy) -> dict:
    """Evaluate offered complete tails without changing the current live actor.

    `scheduler` is the restored live frozen SELL instance BEFORE its current
    action, not a new actor constructed at a late observation. RILL controls
    compatibility, case iteration and one cooperative budget. T04 controls all
    mechanics. These dependencies are supplied rather than copied here.

    The paired values are terminal OWN cash only when end_step is the final
    executable decision. Earlier results remain unvalued prefixes. Rival cash
    is unknown: T04 models declared pre-market external flows, not simultaneous
    paired rival actions. No route recommendation or win probability is made.
    """
    routes = tuple(route_ids)
    incumbent = scheduler.controller.cur
    if incumbent not in routes:
        raise ValueError("Include the current route for paired own-cash comparison")
    facade = SellRouteView(scheduler, configuration)

    def fork(view):
        actor = fork_scheduler(view.scheduler)
        if actor is view.scheduler or actor.controller is view.scheduler.controller:
            raise ValueError("Supply an independent whole-actor fork")
        return SellRouteView(actor, view.configuration)

    raw = replay_routes(facade, routes, observation, configuration, engine,
                        simulate_bundle, scenarios=scenarios, end_step=end_step,
                        fork_controller=fork, limits=limits)
    terminal = int(end_step) == int(configuration.get("episodeSteps", 720)) - 2
    by_key = {(case["offered_route"], case["scenario_id"]): case for case in raw["cases"]}
    comparisons = []
    for route_id in routes:
        for scenario_id in scenarios:
            control = by_key.get((incumbent, scenario_id))
            candidate = by_key.get((route_id, scenario_id))
            complete = bool(control and candidate and control["status"] ==
                            candidate["status"] == "complete")
            comparisons.append({
                "route": route_id, "scenario_id": scenario_id,
                "incumbent": incumbent, "complete_pair": complete,
                "terminal_own_cash_delta": (
                    candidate["final_cash"] - control["final_cash"]
                    if complete and terminal else None),
                "rival_cash_delta": None,
                "reason": ("conditional_terminal_own_cash" if complete and terminal
                           else "nonterminal_prefix" if complete else "incomplete_pair"),
            })
    return {
        "schema": "titan.sell-tail-value.v1", "complete": raw["complete"],
        "terminal_horizon": terminal, "incumbent": incumbent,
        "comparisons": comparisons, "replay": raw, "selection": None,
        "scope": "Full copied SELL actor through existing RILL/T04. Conditional "
                 "own-state value, not simultaneous rival utility, calibrated "
                 "prediction, live selection or new game evidence.",
    }
