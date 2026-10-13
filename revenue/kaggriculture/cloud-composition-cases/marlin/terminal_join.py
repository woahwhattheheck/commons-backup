# SPDX-License-Identifier: Apache-2.0
"""Optional T05 continuation joined to the existing ordered SELL instance.

The caller supplies the already-loaded OSPREY composition and integrated agent.
No parent is constructed here, and no existing component is modified. This is a
research arm, not a change to the selected default or its experiment registry.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def normalized(observation: Mapping[str, Any], configuration=None):
    cfg = dict(configuration or {})
    obs = dict(observation)
    turns = int(cfg.get('turnsPerDay', 24))
    step = obs.get('step')
    obs['step'] = int(step if step is not None else
                      int(obs['day']) * turns + int(obs['hour']))
    return obs, cfg


class TerminalActionJoin:
    """Transform one supplied action, with its matching T05 continuation.

    `composition` is cloud-terminal-sell/composition.py from PR9933. `execution`
    is the caller's existing OrderedSelectedSell. The existing forecast owns its
    reference-sale-dependent worker continuation; ATLAS owns ordered transfers;
    the existing seller owns market selection. No future parent is called.
    """
    def __init__(self, composition, execution):
        self.composition = composition
        self.execution = execution
        self.planner = composition.terminal.Planner()
        self.last_packet = None
        self.last_selected = None
        self.last_future = {}
        self.diagnostics = {}

    def reset(self):
        self.planner = self.composition.terminal.Planner()
        self.last_packet = self.last_selected = None
        self.last_future = {}

    def transform(self, observation, configuration, selected_action, *,
                  own_future_actions=None, reservations=None, sell=True):
        obs, cfg = normalized(observation, configuration)
        now = obs['step']
        start, final = self.composition.terminal_bounds(cfg)
        if not start <= now <= final:
            raise ValueError('TerminalActionJoin requires the T05 final-day window')
        self.last_packet = self.last_selected = None
        self.last_future = {}
        self.diagnostics = {'parent_calls': 0, 'step': now, 'status': 'planning'}
        # Commit the live planner only after a complete packet exists. A failed
        # projection must not consume its queue before the caller's fallback.
        trial = deepcopy(self.planner)
        selected = trial.act(obs, deepcopy(selected_action), cfg,
                             own_future_actions=own_future_actions)
        self.last_selected = deepcopy(selected)
        if not sell:
            self.planner = trial
            self.diagnostics['status'] = 'terminal_without_sell'
            return selected
        route, _ = self.composition.forecast_terminal(obs, cfg, selected, trial)
        end = min(final, now + self.execution.seller.horizon)
        future = {step: route[step] for step in range(now + 1, end + 1)}
        packet = self.execution.prepare(obs, cfg, selected,
                                        future_actions=future, end_step=end)
        self.last_future, self.last_packet = deepcopy(future), packet
        # The generic fallback keeps the selected terminal action. Substituting
        # the old parent action here would desynchronize the committed queue.
        out = self.execution.transform(obs, cfg, selected, prepared=packet,
                                       reservations=reservations,
                                       fallback_action=selected)
        self.planner = trial
        self.diagnostics.update(status='terminal_ordered_sell', end_step=end,
                                seller=deepcopy(self.execution.diagnostics),
                                continuation='T05 reference-sales conditional')
        return out


class IntegratedTerminalAgent:
    """Optional final-day arm around the already-constructed integrated policy.

    The supported parent is the pinned one-way cap producer. Before T05's start,
    and when it still owns an active errand, use integrated.transform unchanged.
    Inside the terminal window T05 owns workers and emits SELL-only orders, so
    the seed-purchase stage has no orders to edit. Observed cargo is projected
    normally; expired prior-day cap lots are not new capacity reservations.
    """
    def __init__(self, integrated, composition, *, terminal=True):
        self.integrated = integrated
        self.terminal_enabled = bool(terminal)
        self.join = TerminalActionJoin(composition, integrated.execution)
        self.diagnostics = {}

    def transform(self, observation, configuration, selected_action, *, reservations=None):
        obs, cfg = normalized(observation, configuration)
        producer = self.integrated.production
        start, final = self.join.composition.terminal_bounds(cfg)
        now = obs['step']
        day = now // int(cfg.get('turnsPerDay', 24))
        compatible = (getattr(producer, 'one_way', False)
                      and day >= getattr(producer, 'last_day', day + 1)
                      and not getattr(producer, 'plans', {}))
        if not self.terminal_enabled or not start <= now <= final or not compatible:
            self.join.reset()
            self.diagnostics = {'status': 'integrated_passthrough', 'parent_calls': 0}
            return self.integrated.transform(obs, cfg, selected_action, reservations=reservations)
        controller = self.integrated.controller
        future = controller.R[controller.cur][now:final + 1]
        try:
            out = self.join.transform(obs, cfg, selected_action,
                                      own_future_actions=future,
                                      reservations=reservations,
                                      sell=self.integrated.sell)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
            self.join.reset()
            self.diagnostics = {'status': 'integrated_fallback',
                                'reason': str(error), 'parent_calls': 0}
            return self.integrated.transform(obs, cfg, selected_action, reservations=reservations)
        self.diagnostics = deepcopy(self.join.diagnostics)
        return out

    def act(self, observation, configuration=None):
        obs, cfg = normalized(observation, configuration)
        selected = self.integrated.production.act(obs)
        result = self.transform(obs, cfg, selected)
        self.diagnostics['producer_calls_in_act'] = 1
        return result

    __call__ = act
