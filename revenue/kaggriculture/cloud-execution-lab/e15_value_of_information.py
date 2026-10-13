# SPDX-License-Identifier: Apache-2.0
"""Bounded value-of-information certificates for existing executable plans.

This module never creates or executes a market action.  It compares caller-
supplied, already-feasible plans across caller-supplied public scenarios.  A
scenario is not a forecast: probabilities stay absent unless the caller supplies
an explicit normalized distribution.  Interval values remain intervals rather
than being collapsed into fabricated point estimates.
"""
from __future__ import annotations

import math


def _interval(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not an economic value')
    if isinstance(value, (int, float)):
        x = float(value)
        if not math.isfinite(x):
            raise ValueError('non-finite economic value')
        return (x, x)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = value
        if any(isinstance(endpoint, bool) or not isinstance(endpoint, (int, float))
               for endpoint in (lo, hi)):
            raise ValueError('invalid value interval')
        lo, hi = float(lo), float(hi)
        if not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
            raise ValueError('invalid value interval')
        return (lo, hi)
    raise ValueError('expected scalar or [low, high] interval')


def _validate(scenario_values):
    if not isinstance(scenario_values, dict) or not scenario_values:
        raise ValueError('at least one scenario is required')
    plans = None
    rows = {}
    for scenario, mapping in scenario_values.items():
        if not isinstance(scenario, str) or not scenario or not isinstance(mapping, dict) or not mapping:
            raise ValueError('scenario values must map named scenarios to plan values')
        names = tuple(sorted(mapping))
        if plans is None:
            plans = names
        elif names != plans:
            raise ValueError('every scenario must score the same executable plans')
        rows[scenario] = {plan: _interval(mapping[plan]) for plan in plans}
    return plans, rows


def _winner_sets(plans, rows):
    possible = {}
    certain = {}
    for scenario, mapping in rows.items():
        best_low = max(mapping[p][0] for p in plans)
        possible[scenario] = [p for p in plans if mapping[p][1] >= best_low]
        certain[scenario] = [
            p for p in plans
            if all(mapping[p][0] >= mapping[q][1] for q in plans if q != p)
        ]
    common = None
    for winners in certain.values():
        ids = set(winners)
        common = ids if common is None else common & ids
    return possible, certain, (common or set())


def information_value(scenario_values, *, probabilities=None, probe_cost=0.0,
                      terminal=False, incumbent_plan=None):
    """Return a source-honest decision-value certificate.

    ``scenario_values`` is ``{scenario: {plan: value_or_[low,high]}}``.  Plans
    must already be executable; this function performs no feasibility search.

    With no probabilities, a ranking flip can justify using *free passive*
    observations that resolve a scenario, but cannot justify paying to probe:
    the expected-VOI lower bound is zero.  With explicit probabilities and
    point-valued scenarios, EVPI is computed exactly; even then this module only
    reports a certificate and never emits the probe action.
    """
    plans, rows = _validate(scenario_values)
    if isinstance(probe_cost, bool):
        raise ValueError('invalid probe cost')
    probe_cost = float(probe_cost)
    if not math.isfinite(probe_cost) or probe_cost < 0:
        raise ValueError('probe cost must be finite and nonnegative')
    if incumbent_plan is not None and incumbent_plan not in plans:
        raise ValueError('incumbent plan was not scored')

    possible, certain, universal = _winner_sets(plans, rows)
    interval_ambiguity = any(lo != hi for mapping in rows.values() for lo, hi in mapping.values())
    decision_invariant = bool(universal)
    stable_plan = (incumbent_plan if incumbent_plan in universal else
                   sorted(universal)[0] if universal else None)

    spread_upper = max(
        max(v[1] for v in mapping.values()) - min(v[0] for v in mapping.values())
        for mapping in rows.values()
    )
    result = {
        'status': 'certified_probability_free',
        'plans': list(plans),
        'possible_winners': possible,
        'certain_winners': certain,
        'universal_winners': sorted(universal),
        'decision_invariant': decision_invariant,
        'passive_information_can_change_choice': not decision_invariant,
        'interval_ambiguity': interval_ambiguity,
        'incumbent_plan': incumbent_plan,
        'selection_without_new_information': stable_plan,
        'probabilities': None,
        'conditional_value_spread_upper_bound': spread_upper,
        'expected_voi_bounds': {'lower': 0.0, 'upper_bound': 0.0 if terminal else spread_upper},
        'terminal': bool(terminal),
        'probe_cost': probe_cost,
        'positive_cost_probe_allowed': False,
        'positive_cost_probe_reason': (
            'terminal_no_payback_window' if terminal else
            'decision_invariant' if decision_invariant else
            'uncalibrated_scenario_probabilities'
        ),
        'collection_recommendation': (
            'none_terminal' if terminal else
            'none_decision_invariant' if decision_invariant else
            'passive_only_if_public_observation_resolves_scenario'
        ),
    }

    if probabilities is None:
        return result
    if interval_ambiguity:
        result.update(status='ambiguous_intervals',
                      positive_cost_probe_reason='interval_values_prevent_exact_expected_value')
        return result
    if set(probabilities) != set(rows):
        raise ValueError('probabilities must cover every scenario exactly')
    weights = {}
    total = 0.0
    for scenario, weight in probabilities.items():
        if isinstance(weight, bool):
            raise ValueError('invalid probability')
        weight = float(weight)
        if not math.isfinite(weight) or weight < 0:
            raise ValueError('invalid probability')
        weights[scenario] = weight
        total += weight
    if abs(total - 1.0) > 1e-9:
        raise ValueError('probabilities must sum to one')

    expected = {
        plan: sum(weights[s] * rows[s][plan][0] for s in rows)
        for plan in plans
    }
    baseline_value = max(expected.values())
    baseline_winners = sorted(p for p, value in expected.items()
                              if abs(value - baseline_value) <= 1e-9)
    if incumbent_plan in baseline_winners:
        baseline_plan = incumbent_plan
    else:
        baseline_plan = baseline_winners[0]
    perfect_value = sum(weights[s] * max(rows[s][p][0] for p in plans) for s in rows)
    evpi = max(0.0, perfect_value - baseline_value)
    net = evpi - probe_cost
    allowed = bool(not terminal and not decision_invariant and evpi > probe_cost)
    result.update(
        status='certified_expected_value', probabilities=weights,
        expected_plan_values=expected, baseline_plan=baseline_plan,
        baseline_expected_value=baseline_value,
        perfect_information_expected_value=perfect_value,
        expected_value_of_perfect_information=evpi,
        information_value_minus_probe_cost=net,
        expected_voi_bounds={'lower': 0.0, 'upper_bound': 0.0 if terminal else evpi},
        positive_cost_probe_allowed=allowed,
        positive_cost_probe_reason=(
            'terminal_no_payback_window' if terminal else
            'decision_invariant' if decision_invariant else
            'expected_information_value_not_above_complete_probe_cost' if not allowed else
            'expected_information_value_strictly_exceeds_complete_probe_cost'
        ),
    )
    return result
