# SPDX-License-Identifier: Apache-2.0
"""Bounded own-tape supply for the current-lot sale valuation experiment."""
from copy import deepcopy


def projected_sales(obs, config, base, farm, private, route, end, item):
    """Project only newly deposited units consumed by represented sell-all rows.

    The initial shed lot is valued separately by the existing optimizer. This
    projection colors later deposits and excludes them from that original lot.
    It follows the chosen own route within the seller's existing same-day
    horizon; it does not predict rival actions or new controller branches.
    """
    from scheduler import post_units
    from frozen_selected import apply_represented_market
    now = int(obs['step'])
    turns = int(config.get('turnsPerDay', 24))
    last = min(int(end), (now // turns + 1) * turns - 1, len(route) - 1)
    f, p = deepcopy(farm), deepcopy(private)
    apply_represented_market(f, p, base.get('market', []), len(f['tiles']))
    new_stock = 0
    sales = []
    for step in range(now + 1, last + 1):
        action = route[step]
        before = max(0, int(p['shed'].get(item, 0)))
        projected = {'step': step, 'player': 0, 'farms': [f, f], 'private': p}
        f, p = post_units(projected, action, config, shed_capacity=10**6)
        total = max(0, int(p['shed'].get(item, 0)))
        # Favor removing new stock first on a represented PICKUP, so uncertain
        # lot identity cannot inflate future sale volume.
        new_stock = max(0, min(total, new_stock + total - before))
        for order in action.get('market', [])[:int(config.get('maxMarketOrdersPerTurn', 10))]:
            if not order:
                continue
            if order[0] in ('BUY_PRODUCT', 'BUY_ANIMAL') and len(order) > 2 and order[1] == item:
                # A purchased future lot needs a cash-feasible queue model.
                return ()
            if order[0] == 'SELL' and len(order) > 2 and order[1] == item:
                requested = max(0, int(order[2]))
                filled = min(total, requested)
                newly_sold = max(0, filled - (total - new_stock))
                if newly_sold and requested >= total:
                    sales.append((step, newly_sold))
                new_stock -= newly_sold
                total -= filled
        apply_represented_market(f, p, action.get('market', []), len(f['tiles']))
    return tuple((step, sum(q for t, q in sales if t == step))
                 for step in sorted({t for t, _ in sales}))
