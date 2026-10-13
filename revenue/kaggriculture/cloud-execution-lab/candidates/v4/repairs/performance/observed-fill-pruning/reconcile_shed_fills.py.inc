def reconcile_shed_fills(post_unit_shed: Mapping[str, int], submitted_action: Any,
                         next_shed: Mapping[str, int], configuration: Any = None, *,
                         after_market_deposits: Any = (), max_states: int = 4096,
                         max_transitions: int = 100_000) -> dict[str, Any]:
    """Infer per-slot shed-changing fills conditional on exact supplied snapshots.

    ``after_market_deposits`` is the ordered sequence of whole carried-inventory
    mappings automatically deposited AFTER the market. Empty means known none;
    None means unknown. Each mapping's item order matters at the capacity limit.
    The stateful adapter derives whether this evidence is needed from the clock.

    Purchases may fill anywhere from zero to requested/capacity. This deliberately
    ignores cash and rival-dependent prices, retaining a superset of real paths.
    All sell fills follow the pinned market's exact ordered stock semantics.
    A singleton interval is therefore a quantity conclusion, NOT a price or
    payment receipt. Bound exhaustion or contradictory evidence returns unknown.
    """
    try:
        before, after = _stock(post_unit_shed), _stock(next_shed)
        capacity, limit, _ = _config(configuration)
        if not isinstance(max_states, int) or isinstance(max_states, bool) or max_states < 1:
            raise ValueError('invalid state budget')
        if (not isinstance(max_transitions, int) or isinstance(max_transitions, bool)
                or max_transitions < 1):
            raise ValueError('invalid transition budget')
        if after_market_deposits is None:
            return _unknown('after_market_deposits_unknown')
        if not isinstance(after_market_deposits, (list, tuple)):
            raise ValueError('deposits must be an ordered sequence')
        deposits = [_stock(x) for x in after_market_deposits]
        queue = submitted_action.get('market', []) if isinstance(submitted_action, dict) else []
        queue = queue if isinstance(queue, list) else []
        orders = [_parse(o, i, limit) for i, o in enumerate(queue)]
    except (ValueError, TypeError, OverflowError):
        return _unknown('invalid_input')

    keys = sorted(set(before) | set(after) | {k for d in deposits for k in d}
                  | {o['item'] for o in orders if o['kind'] in ('sell', 'buy')})
    index = {k: i for i, k in enumerate(keys)}
    wanted = tuple(after.get(k, 0) for k in keys)
    # Necessary coordinate bounds only: a future sale cannot remove more than
    # its requested/per-slot maximum, and a future purchase/deposit cannot add
    # more than its own maximum. Shared capacity and ordered deposits remain
    # in the original exact forward calculation below. These bounds may retain
    # impossible paths, but cannot discard any path matching the observation.
    active_orders = [o for o in orders if o['kind'] in ('sell', 'buy')]
    prune = any(o['kind'] == 'buy' for o in active_orders)
    if prune:
        future_buys, future_sales = [0] * len(keys), [0] * len(keys)
        deposit_max = [sum(d.get(k, 0) for d in deposits) for k in keys]
        for order in active_orders:
            totals = future_sales if order['kind'] == 'sell' else future_buys
            bound = min(order['requested'], MAX_SLOT_UNITS)
            if order['kind'] == 'buy':
                bound = min(bound, capacity)
            totals[index[order['item']]] += bound
    zero = (0,) * len(orders)
    states = {tuple(before.get(k, 0) for k in keys): (zero, zero)}
    peak, transitions = 1, 0
    for order in active_orders:
        kind, slot = order['kind'], order['slot']
        target = {}
        item_index = index[order['item']]
        if prune:
            bound = min(order['requested'], MAX_SLOT_UNITS)
            totals = future_sales if kind == 'sell' else future_buys
            totals[item_index] -= bound if kind == 'sell' else min(bound, capacity)
            lower_stock = [max(0, wanted[i] - future_buys[i] - deposit_max[i])
                           for i in range(len(keys))]
            upper_stock = [wanted[i] + future_sales[i] for i in range(len(keys))]
        for stock, (lo, hi) in states.items():
            if prune and any(not lower_stock[i] <= quantity <= upper_stock[i]
                             for i, quantity in enumerate(stock) if i != item_index):
                continue
            if kind == 'sell':
                quantity = min(order['requested'], stock[item_index], MAX_SLOT_UNITS)
                if prune and not lower_stock[item_index] <= stock[item_index] - quantity <= upper_stock[item_index]:
                    continue
                quantities = (quantity,)
            else:
                ceiling = min(order['requested'], max(0, capacity - sum(stock)), MAX_SLOT_UNITS)
                first = max(0, lower_stock[item_index] - stock[item_index])
                last = min(ceiling, upper_stock[item_index] - stock[item_index])
                if first > last:
                    continue
                # Enumerate the complete observation-compatible relaxed range;
                # never sample quantities or discard genuine ambiguity.
                if transitions + last - first + 1 > max_transitions:
                    return _unknown('transition_budget_exceeded', peak_states=peak,
                                    transitions=transitions)
                quantities = range(first, last + 1)
            for quantity in quantities:
                transitions += 1
                if transitions > max_transitions:
                    return _unknown('transition_budget_exceeded', peak_states=peak,
                                    transitions=transitions - 1)
                new_stock = list(stock)
                new_stock[item_index] += -quantity if kind == 'sell' else quantity
                new_lo, new_hi = list(lo), list(hi)
                new_lo[slot] = new_hi[slot] = quantity
                _merge(target, tuple(new_stock), (tuple(new_lo), tuple(new_hi)))
                if len(target) > max_states:
                    return _unknown('state_budget_exceeded', peak_states=len(target),
                                    transitions=transitions)
        states = target
        peak = max(peak, len(states))

    matched = []
    for stock, bounds in states.items():
        final = list(stock)
        used = sum(final)
        for deposit in deposits:
            for item, quantity in deposit.items():
                admitted = min(quantity, max(0, capacity - used))
                final[index[item]] += admitted
                used += admitted
        if tuple(final) == wanted:
            matched.append(bounds)
    if not matched:
        return _unknown('observed_shed_not_explained', peak_states=peak,
                        transitions=transitions, compatible_states=0)
    lower = [min(b[0][i] for b in matched) for i in range(len(orders))]
    upper = [max(b[1][i] for b in matched) for i in range(len(orders))]
    rows = []
    for order in orders:
        slot, kind = order['slot'], order['kind']
        row = dict(order)
        if kind == 'not_inferred':
            row.update(fill_min=None, fill_max=None)
        else:
            row.update(fill_min=lower[slot], fill_max=upper[slot])
        rows.append(row)
    ambiguous = any(o['kind'] in ('sell', 'buy') and o['fill_min'] != o['fill_max'] for o in rows)
    return {'status': 'ambiguous' if ambiguous else 'reconciled',
            'reason': 'compatible_shed_paths', 'orders': rows,
            'cash_receipts': None, 'compatible_states': len(matched),
            'peak_states': peak, 'transitions': transitions,
            'method': 'bounded_own_shed_superset',
            'non_shed_orders_inferred': False}
