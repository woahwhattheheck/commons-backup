# SPDX-License-Identifier: Apache-2.0
"""One public-observation branch after an identical complete-plan prefix.

This module consumes an exact sale model and caller-feasible plans. It creates
no controller, estimates no probabilities, and never receives a realized rival
action. The tie objective is Pareto improvement, then worst margin, then sum of
included-column margins. The sum is a deterministic tie-break, not expectation.
"""
from copy import deepcopy


def weak_choice(rows, columns):
    """Baseline on exact ties; reject any loss within the information set."""
    selected, best = 0, (0, 0)
    for i, row in enumerate(rows):
        values = [row[j] for j in columns]
        key = min(values), sum(values)
        if key[0] >= 0 and key > best:
            selected, best = i, key
    return selected


def compile_policy(model, plans, quantity, streams, branch, absorption):
    """Return a table and causal decision map over a coarse public projection.

    All plans have the same sales strictly before branch. Grouping uses only
    observed shared item inventory; ignoring other public facts retains extra
    hypotheses conservatively. Equal inventories never identify rival quantity
    or slot, and floor-priced nonadmission remains grouped. Full correlated
    streams remain intact; no per-date recombination is performed.
    """
    if not model.now < branch <= model.end or not 1 <= len(plans) <= 9:
        raise ValueError('One future branch and at most nine complete plans')
    if not 1 <= len(streams) <= 32:
        raise ValueError('One to 32 complete rival streams')
    canonical = [tuple((int(t), int(q)) for t, q in p['sales'] if q) for p in plans]
    prefix = tuple((t, q) for t, q in canonical[0] if t < branch)
    for plan in canonical:
        if sum(q for _, q in plan) != quantity or any(q < 0 for _, q in plan):
            raise ValueError('Every plan must sell the same complete lot')
        if len(dict(plan)) != len(plan) or any(not model.now <= t <= model.end for t, _ in plan):
            raise ValueError('Unique legal sale dates')
        if tuple((t, q) for t, q in plan if t < branch) != prefix:
            raise ValueError('Executed prefixes must be identical')
    receipts = [[model.score(p, quantity, tuple(map(tuple, r)), a, True)
                 for _, r, a in streams] for p in canonical]
    baseline = receipts[0]
    deltas = [[int(x[0] - b[0]) for x, b in zip(row, baseline)] for row in receipts]
    groups = {}
    for column, (_, rival, alignment) in enumerate(streams):
        inventory = model.inventory
        own_orders, rival_orders = dict(prefix), dict(rival)
        for step in range(model.now, branch):
            _, _, inventory = model.joint(inventory, own_orders.get(step, 0),
                                           rival_orders.get(step, 0), alignment)
            inventory -= absorption(model.item, step, model.shops, model.config)
        groups.setdefault(str(inventory), []).append(column)
    choices = {key: weak_choice(deltas, columns) for key, columns in groups.items()}
    causal = [0] * len(streams)
    for key, columns in groups.items():
        for column in columns:
            causal[column] = deltas[choices[key]][column]
    static = weak_choice(deltas, range(len(streams)))
    return {'branch': branch, 'prefix': [list(x) for x in prefix],
            'plans': deepcopy(plans), 'deltas': deltas, 'receipts': receipts,
            'groups': groups, 'choices': choices, 'causal_deltas': causal,
            'static_choice': static, 'static_deltas': deltas[static],
            'active': max(causal) > 0, 'worst_margin': min(causal),
            'objective': 'nonnegative_each_column_then_max_min_then_sum',
            'probabilities': None, 'alpha': 0,
            'observation_projection': 'shared market inventory for the lot product'}


def choose_observed(policy, observation, item):
    """Unknown public state uses the entire supplied fallback (None)."""
    if int(observation['step']) != policy['branch']:
        return None
    key = str(int(observation['market']['inventory'][item]))
    return policy['choices'].get(key)
