# SPDX-License-Identifier: Apache-2.0
"""Internal research callback over unchanged HAZEL / FLOW / DATE components.

This module creates no controller, scenario probabilities or release package.
The caller supplies the live controller, mechanics, and explicit scenarios.
"""
from __future__ import annotations
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
import time


def choose_dated(controller: Any, observation: Mapping, configuration: Mapping,
                 mechanics: Any, *, hazel: Any, flow: Any, date: Any,
                 scenarios: Sequence[Any], seconds: float = .20,
                 max_units: int = 100_000) -> dict:
    """Use one existing selection seam and retain a complete paired cash report.

    This is a conditional market-volume model. It does not establish physical
    future fills or a calibrated probability of future shops/rival orders.
    An incomplete or late computation retains the live incumbent.
    """
    started = time.perf_counter()
    original = controller.cur
    report: dict[str, Any] = {'model': None, 'ranking': None, 'elapsed': None}
    def selector(offers, obs):
        remaining = seconds - (time.perf_counter() - started)
        if remaining <= 0:
            report['model'] = {'complete': False, 'reason': 'quotation_budget', 'rows': []}
            return offers[0].route_id
        model = flow.evaluate_scenarios(offers, obs, configuration, mechanics,
                                       scenarios, seconds=remaining,
                                       max_units=max_units, retain_trace=False)
        report['model'] = model
        if not model['complete']:
            return offers[0].route_id
        ranker = date.DatedSelector(flow.as_cash_scenarios(model, date.CashScenario))
        chosen = ranker(offers, obs)
        report['ranking'] = ranker.last_report
        if time.perf_counter() - started > seconds:
            report['late'] = True
            return offers[0].route_id
        return chosen
    outer = hazel.choose_before_action(controller, observation, configuration,
                                       mechanics, selector=selector)
    report.update(outer=outer, elapsed=time.perf_counter()-started,
                  applied_route=controller.cur,
                  changed=controller.cur != original,
                  semantics='Conditional scheduled-volume model; no future fill certificate')
    return report
