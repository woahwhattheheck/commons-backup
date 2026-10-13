# SPDX-License-Identifier: Apache-2.0
"""Optional late recheck of two existing complete Arlene production routes.

The original actor runs unchanged through decision 576, including its decision
at 433 and every resulting sale. At 577 only, current public MILK inventory may
select the other stored-prefix-compatible complete route before the SAME actor
is called once. This is a research arm, not an economic/feasibility guarantee.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

MAIN = '7015cc00acfa4922'
MILK_EXIT = 'a84d06f1d12add7c'
CHECKPOINT = 577
THRESHOLD = 10067


class LateMilkChoice:
    """Use one wrapper and its original actor/controller for one match.

    ``call`` is the original ``actor.act(obs, cfg)`` bound method; ``controller``
    is that SAME actor's Arlene controller. Its routes, observations, SELL state,
    original decisions, and source are never replaced or reconstructed. The
    choice uses no evaluator seed, future shop, opponent private state or replay.

    Prefix compatibility is a stored-program property, not actual trajectory
    equivalence: Arlene's sale overrides depend on the future route. This arm
    preserves the original live prefix before its one later reconsideration.
    """

    def __init__(self, call: Callable, controller: Any, *, enabled: bool = True):
        if not callable(call):
            raise TypeError('Supply the existing two-argument actor method')
        self.call = call
        self.controller = controller
        self.enabled = bool(enabled)
        self.attempted = False
        self.last_choice: dict[str, Any] | None = None
        self.calls = 0

    def reconsider(self, observation: Mapping, configuration: Mapping | None = None) -> dict | None:
        """Propose no new route; change current route once at the named boundary."""
        cfg = configuration or {}
        try:
            step = observation.get('step')
            if step is None:
                step = int(observation['day']) * int(cfg.get('turnsPerDay', 24)) + int(observation['hour'])
            if type(step) is not int or step != CHECKPOINT or self.attempted:
                return deepcopy(self.last_choice)
            self.attempted = True
            before = self.controller.cur
            report = {'step': step, 'before': before, 'after': before,
                      'changed': False, 'reason': 'disabled' if not self.enabled else 'unchanged',
                      'threshold': THRESHOLD, 'inventory': None,
                      'scope': 'existing stored-prefix-compatible routes; no future-value guarantee'}
            self.last_choice = report
            if not self.enabled:
                return deepcopy(report)
            # These existing programs were authored for this exact game length
            # and daily clock. Keep the original actor in other configurations.
            if int(cfg.get('turnsPerDay', 24)) != 24 or int(cfg.get('episodeSteps', 720)) != 720:
                report['reason'] = 'other_configuration'
                return deepcopy(report)
            if before not in (MAIN, MILK_EXIT):
                report['reason'] = 'other_route'
                return deepcopy(report)
            value = observation['market']['inventory']['MILK']
            if type(value) is not int:
                report['reason'] = 'inventory_unavailable'
                return deepcopy(report)
            report['inventory'] = value
            desired = MILK_EXIT if value >= THRESHOLD else MAIN
            report['desired'] = desired
            if desired == before:
                return deepcopy(report)
            if desired not in self.controller.R or not self.controller._switch_ok(desired, step):
                report['reason'] = 'program_prefix_differs'
                return deepcopy(report)
            # Preserve all live controller and SELL state. The existing
            # future_sells implementation refreshes its cache when cur changes.
            self.controller.cur = desired
            report.update(after=desired, changed=True, reason='late_public_recheck')
            return deepcopy(report)
        except (AttributeError, KeyError, TypeError, ValueError, IndexError):
            if self.last_choice is None:
                self.last_choice = {'step': CHECKPOINT, 'changed': False, 'reason': 'input_unavailable'}
            else:
                self.last_choice['reason'] = 'input_unavailable'
            return deepcopy(self.last_choice)

    def act(self, observation: Mapping, configuration: Mapping | None = None):
        # Normalize the public shared clock, as the existing evaluator does for
        # each actor. No mutation of the caller's observation or configuration.
        cfg = dict(configuration or {})
        obs = dict(observation)
        if obs.get('step') is None:
            obs['step'] = int(obs['day']) * int(cfg.get('turnsPerDay', 24)) + int(obs['hour'])
        self.reconsider(obs, cfg)
        self.calls += 1
        return self.call(obs, cfg)

    __call__ = act


def wrap_sell(actor, *, enabled=True):
    """Consume an already-created frozen SellScheduler; construct no controller."""
    return LateMilkChoice(actor.act, actor.controller, enabled=enabled)
