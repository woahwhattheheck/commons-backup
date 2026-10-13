# SPDX-License-Identifier: MIT OR CC-BY-4.0
# Verbatim function excerpt from Commons/SORREL forecast.py at 0a1f0ec.
# Used as an independent conditional-receipt cross-check, not a new price model.
from collections import defaultdict


def project_sale_timeline(initial_inventory, sales, horizons, quote, demand_before):
    """Conditional batches with floor-aware supply and same-unit joint quotes.

    sales maps action step to {seat: quantity}; each product's two seat batches
    are assumed aligned at one order slot, flattened across that seat's tiles.
    Actual cross-product order indices are unknown. This is an explicit scenario
    convention, not an opponent order prediction or a guarantee of revenues.
    demand_before(step) is cumulative exogenous town consumption before step.
    """
    inventory = initial_inventory
    previous_demand = 0
    sold = defaultdict(int); admitted = defaultdict(int); cash = defaultdict(int)
    snapshots = {}; timeline = []
    for step in sorted(set(sales) | set(horizons)):
        demand = demand_before(step)
        inventory -= demand - previous_demand
        previous_demand = demand
        quantities = sales.get(step, {})
        step_supply = defaultdict(int); step_cash = defaultdict(int)
        for unit in range(max(quantities.values(), default=0)):
            # Both seats quote before either commit; $1 pays but adds no supply.
            price = quote(inventory)
            active = [seat for seat, qty in quantities.items() if unit < qty]
            for seat in active:
                sold[seat] += 1; cash[seat] += price; step_cash[seat] += price
                if price > 1:
                    admitted[seat] += 1; step_supply[seat] += 1
            if price > 1:
                inventory += len(active)
        if quantities:
            timeline.append({'step': step, 'sale_units_by_seat': dict(quantities),
                             'market_supply_units_by_seat': dict(step_supply),
                             'conditional_cash_by_seat': dict(step_cash)})
        if step in horizons:
            snapshots[step] = {'inventory': inventory, 'sale_units_by_seat': dict(sold),
                               'market_supply_units_by_seat': dict(admitted),
                               'conditional_cash_by_seat': dict(cash)}
    return snapshots, timeline
