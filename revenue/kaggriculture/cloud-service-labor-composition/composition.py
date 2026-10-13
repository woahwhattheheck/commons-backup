# SPDX-License-Identifier: MIT
"""T04 service + T10 labor research composition with one authoritative Arlene.

No source policy is rewritten. Forecasts clone the pinned intact Arlene value
state, not an arbitrary nested wrapper. The engine is shared read-only code;
all observed game state is copied by the original component oracles. By default,
T04 forecasts use the intact-parent continuation (with its current selected
labor action fixed), not a recursive reoptimization of every future hire. This
is a conditional model choice, measured in the full-game factorial.
"""
from __future__ import annotations

from collections import Counter
from copy import copy, deepcopy
from typing import Any, Mapping


class Composition:
    """One instance per actor/match; no hidden seed or future-replay input."""

    def __init__(self, arlene: Any, labor_module: Any, service_module: Any,
                 engine: Any, configuration: Mapping[str, Any] | None = None,
                 *, service: bool = True, labor: bool = True,
                 forecast_labor: bool = False):
        self.base = arlene.Agent()
        self.labor_module = labor_module
        self.engine = engine
        # Preserve the component's explicit public configuration subset.
        self.configuration = labor_module._configuration(configuration)
        self.hiring = (labor_module.HiringAgent(self.base, engine, mode="reserve",
                                               configuration=self.configuration)
                       if labor else None)
        self.forecast_labor = forecast_labor
        self.calls = 0
        self.parent_calls = 0
        self.forks = 0
        self.service_enabled, self.labor_enabled = service, labor
        self._service = (service_module.make_policy(
            self._current, engine, fork_parent=self.fork_parent)
            if service else None)

    def _current(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        self.parent_calls += 1
        return (self.hiring.act(observation) if self.hiring is not None
                else self.base.act(observation))

    def fork_parent(self):
        """Isolate live route choice and mutable hiring diagnostics.

        The pinned Arlene Agent rebinds cur/_fs/_fs_for; it never mutates its
        decoded route R or an already-built suffix cache. Sharing those exact
        values is intentional, not a general deepcopy substitute. T10's own
        project_shift sees ONLY this intact Agent, never a Composition.
        """
        self.forks += 1
        base = copy(self.base)
        # Bound speculative work: default forecasts keep the intact parent
        # continuation. Actual current hiring remains selected by T10. The
        # recursive optimization variant is retained explicitly for research.
        if self.hiring is None or not self.forecast_labor:
            return base.act
        fork = self.labor_module.HiringAgent(
            base, self.engine, mode=self.hiring.mode,
            configuration=dict(self.hiring.configuration))
        fork.last_decision = deepcopy(self.hiring.last_decision)
        fork.counts = Counter(self.hiring.counts)
        return fork.act

    def act(self, observation: Mapping[str, Any], configuration=None) -> dict[str, Any]:
        self.calls += 1
        before = self.parent_calls
        result = (self._service(observation, self.configuration) if self._service
                  else self._current(observation))
        if self.parent_calls != before + 1:
            raise RuntimeError("Actual parent must be evaluated exactly once per action")
        return result
