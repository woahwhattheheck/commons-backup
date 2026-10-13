"""Public unlock support plus an explicitly assumed independent-uniform model.

The engine uses a fixed hidden seed and consumes farm-dependent random draws
before choosing a shop. This is NOT a posterior over that seed or an empirical
probability estimate. No scenario payoff, policy, controller or seed is read.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping, Sequence

from town_demand import DemandRules, build_schedule


def _mass(value: Fraction) -> dict[str, Any]:
    return {'numerator': value.numerator, 'denominator': value.denominator,
            'value': float(value)}


def buyer_arrivals(observation: Any, configuration: Any, rules: DemandRules, *,
                   buyers: Sequence[str], market_steps: Sequence[int] = (),
                   model: str | None = None) -> dict[str, Any]:
    """First FUTURE buyer support; weights exist only for the named assumption.

    A first-arrival category contains many complete shop paths. It is not one
    economic scenario, so the result cannot supply weights to a two-tail payoff
    table unless every category's conditional outcomes are separately supplied.
    Existing buyer instances are reported separately from future arrivals.
    """
    if model not in (None, 'independent_uniform'):
        raise ValueError('Use no probability model or explicitly independent_uniform')
    names = tuple(name for name, _ in rules.shops)
    targets = tuple(buyers)
    if (not targets or len(set(targets)) != len(targets)
            or set(targets) - set(names)):
        raise ValueError('buyers must be distinct shop names from the source catalogue')
    schedule = build_schedule(observation, configuration, rules, future_shops=None)
    if schedule.start_step > schedule.end_step:
        raise ValueError('No remaining market in this observation')
    queries = tuple(market_steps)
    if any(isinstance(s, bool) or not isinstance(s, int)
           or not schedule.start_step <= s <= schedule.end_step for s in queries):
        raise ValueError('market_steps must be playable integer steps in this window')
    get = configuration.get if isinstance(configuration, Mapping) else (
        lambda name, default: getattr(configuration, name, default))
    interval = max(1, int(get('townShopSellInterval', 4)))
    p = Fraction(len(targets), len(names))
    q = 1 - p
    rows = []
    for i, after in enumerate(schedule.unlock_after_steps):
        active = after + 1
        per_type = {}
        for target in targets:
            signature = rules.signature(target, schedule.products)
            by_market = {}
            for step in queries:
                hi = step - 1
                ticks = max(0, hi // interval - (active - 1) // interval)
                by_market[str(step)] = dict(zip(schedule.products, (v*ticks for v in signature)))
            per_type[target] = by_market
        rows.append({'draw_index': i + 1, 'unlock_after_action': after,
                     'first_visible_step': active,
                     'has_remaining_market': active <= schedule.end_step,
                     'first_buyer_mass': _mass(q**i*p) if model else None,
                     'one_instance_removed_before_market': per_type})
    n = len(rows)
    return {'schema': 'town.first-future-buyer.v1',
            'start_step': schedule.start_step, 'end_step': schedule.end_step,
            'buyer_types': list(targets), 'source_shop_types': list(names),
            'observed_buyer_instances': sum(s in targets for s in schedule.observed_shops),
            'remaining_draws': n, 'full_identity_paths': len(names)**n,
            'identity_path_count_scope': 'cartesian shop-choice combinations, not verified hidden-seed reachability',
            'first_arrivals': rows,
            'no_future_buyer_mass': _mass(q**n) if model else None,
            'at_least_one_future_buyer_mass': _mass(1-q**n) if model else None,
            'model': model,
            'model_is_hidden_seed_posterior': False,
            'model_is_empirically_calibrated': False,
            'draw_categories_are_complete_economic_scenarios': False,
            'conditional_payoffs_supplied': False,
            'scenario_weights_for_ranker': None,
            'interpretation': 'first-future-arrival support; subsequent shops and all economic outcomes remain unspecified'}
