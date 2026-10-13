# SPDX-License-Identifier: Apache-2.0
"""Small-state exhaustive test oracle: no reference parser, merging, or pruning.

This models the existing reconciler's relaxed inventory semantics, not the
full Kaggle interpreter. It must not be used as a runtime economics evaluator.
"""
from __future__ import annotations

from copy import deepcopy

PRODUCTS = {'WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON',
            'EGG', 'MILK', 'WOOL', 'FERTILIZER'}
ANIMALS = {'COW', 'GOOSE', 'SHEEP'}
CROPS = {'WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON'}


def describe(queue, limit):
    rows = []
    for slot, order in enumerate(queue):
        row = dict(slot=slot, type=None, item=None, requested=None, kind='ignored')
        if isinstance(order, list) and order and isinstance(order[0], str):
            operation = order[0]
            row['type'] = operation
            if operation in {'HIRE', 'BUY_LAND'}:
                if slot < limit:
                    row['kind'] = 'not_inferred'
            elif operation in {'SELL', 'BUY_PRODUCT', 'BUY_ANIMAL', 'BUY_SEED'} and len(order) >= 3:
                try:
                    amount = int(order[2])
                except (TypeError, ValueError, OverflowError):
                    amount = 0
                item = order[1]
                if isinstance(item, str) and amount > 0:
                    row.update(item=item, requested=amount)
                    if slot < limit:
                        if operation == 'SELL' and item in PRODUCTS:
                            row['kind'] = 'sell'
                        elif ((operation == 'BUY_PRODUCT' and item in {'WHEAT', 'FERTILIZER'})
                              or (operation == 'BUY_ANIMAL' and item in ANIMALS)):
                            row['kind'] = 'buy'
                        elif operation == 'BUY_SEED' and item in CROPS:
                            row['kind'] = 'not_inferred'
        rows.append(row)
    return rows


def paths(before, action, capacity, limit):
    """Keep every individual path; never merge away fill-vector correlation."""
    queue = action.get('market', []) if isinstance(action, dict) else []
    queue = queue if isinstance(queue, list) else []
    rows = describe(queue, max(1, limit))
    frontier = [(dict(before), [0] * len(rows))]
    for row in rows:
        if row['kind'] not in {'sell', 'buy'}:
            continue
        expanded = []
        for stock, vector in frontier:
            item = row['item']
            available = stock.get(item, 0)
            if row['kind'] == 'sell':
                choices = [min(available, row['requested'], 99999)]
            else:
                choices = range(min(row['requested'], max(0, capacity - sum(stock.values())), 99999) + 1)
            for quantity in choices:
                state, fills = dict(stock), list(vector)
                state[item] = available + quantity * (1 if row['kind'] == 'buy' else -1)
                fills[row['slot']] = quantity
                expanded.append((state, fills))
        frontier = expanded
    return rows, frontier


def deposited(stock, deposits, capacity):
    final = dict(stock)
    for inventory in deposits:
        for item, count in inventory.items():
            room = max(0, capacity - sum(final.values()))
            final[item] = final.get(item, 0) + min(count, room)
    return final


def canonical(stock):
    return tuple(sorted((item, count) for item, count in stock.items() if count != 0))


def reconcile(case):
    cfg = case.get('configuration') or {}
    capacity = int(cfg.get('shedCapacity', 100))
    rows, frontier = paths(case['post_unit_shed'], case['submitted_action'], capacity,
                           int(cfg.get('maxMarketOrdersPerTurn', 10)))
    expected = canonical(case['next_shed'])
    matches = [(stock, vector) for stock, vector in frontier
               if canonical(deposited(stock, case.get('after_market_deposits', ()), capacity)) == expected]
    if not matches:
        return dict(status='unknown', reason='observed_shed_not_explained', orders=[], cash_receipts=None)
    out = deepcopy(rows)
    for row in out:
        index = row['slot']
        if row['kind'] == 'not_inferred':
            row.update(fill_min=None, fill_max=None)
        else:
            row.update(fill_min=min(v[index] for _, v in matches),
                       fill_max=max(v[index] for _, v in matches))
    ambiguous = any(row['kind'] in {'buy', 'sell'} and row['fill_min'] != row['fill_max'] for row in out)
    return dict(status='ambiguous' if ambiguous else 'reconciled', reason='compatible_shed_paths',
                orders=out, cash_receipts=None,
                compatible_states=len({canonical(stock) for stock, _ in matches}),
                method='bounded_own_shed_superset', non_shed_orders_inferred=False)
