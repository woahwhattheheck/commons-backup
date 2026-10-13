# SPDX-License-Identifier: Apache-2.0
"""Spend a certified empty harvest turn on delivery before the last market.

This is a bounded producer proposal, not a market forecast. It keeps the
worker's remaining WATER/HARVEST tasks in order, then uses spare time to DROP.
Normal worker expiry establishes an equivalent end-of-day state.
Only the deterministic unit/delivery/reset projection is certified here;
actual sale receipts require execution through the selected SELL consumer.
"""
from copy import deepcopy

from ordered_yield import account_ordered_yield, apply_joint_units

MOVES = {'NORTH': (0, -1), 'SOUTH': (0, 1),
         'EAST': (1, 0), 'WEST': (-1, 0)}
TASKS = {'WATER', 'HARVEST'}


def unit(row, actor):
    if actor == 0:
        return row.get('farmer', ['PASS'])
    hands = row.get('hands', [])
    return hands[actor - 1] if actor <= len(hands) else ['PASS']


def set_unit(row, actor, action):
    if actor == 0:
        row['farmer'] = list(action)
    else:
        hands = row.setdefault('hands', [])
        while len(hands) < actor:
            hands.append(['PASS'])
        hands[actor - 1] = list(action)


def move(position, action, board):
    delta = MOVES.get(action[0] if action else '')
    if delta:
        target = (position[0] + delta[0], position[1] + delta[1])
        if 0 <= target[0] < board and 0 <= target[1] < board:
            return target
    return tuple(position)


def path(start, goal):
    return ([['EAST' if goal[0] > start[0] else 'WEST']]
            * abs(goal[0] - start[0])
            + [['SOUTH' if goal[1] > start[1] else 'NORTH']]
            * abs(goal[1] - start[1]))


def _stock(private):
    return (sum(private['shed'].values())
            + sum(sum(inv.values()) for inv in private['inventories']))


def _project(mechanics, obs, config, rows, now, *, require_capacity=False):
    """Conditional unit projection with no credit for future market sales.

    Production planning excludes the optional DROP. Capacity is enforced again
    from the real observation when that DROP is about to execute.
    """
    farm = deepcopy(obs['farms'][obs['player']])
    private = deepcopy(obs['private'])
    capacity = int(config.get('shedCapacity', 100))
    per_day = int(config.get('turnsPerDay', 24))
    deliveries = []
    max_stock = _stock(private)
    for offset, row in enumerate(rows):
        step = now + offset
        # Future shared-input availability is not inferred from a market tape.
        if any(unit(row, i) and unit(row, i)[0] == 'PICKUP'
               for i in range(1 + len(farm['hands']))):
            return None, 'shared_pickup_in_window'
        # The producer can turn an authored no-op on a weed into DIG. A raw
        # route certificate may not substitute for that live intervention.
        for i, position in enumerate([farm['farmer'], *farm['hands']]):
            tile = farm['tiles'][position[1]][position[0]]
            unit_command = unit(row, i)
            if (isinstance(tile, dict) and tile.get('kind') == 'WEED'
                    and (not unit_command or unit_command[0] not in {*MOVES, 'DIG'})):
                return None, 'live_weed_repair_in_window'
        stock_before = _stock(private)
        report = apply_joint_units(mechanics, farm, private, row, config,
                                   step // per_day)
        # This upper bound does not subtract FEED/PLACE consumption or credit
        # later SELLs. Consequently it also rules out intermediate DROP loss.
        produced = sum(
            max(0, qty - receipt['inventory_before'].get(item, 0))
            for receipt in report['unit_receipts']
            if receipt['effective_action'] and receipt['effective_action'][0]
            in ('HARVEST', 'COLLECT_FERTILIZER')
            for item, qty in receipt['inventory_after'].items())
        max_stock = max(max_stock, stock_before + produced, _stock(private))
        if require_capacity and max_stock > capacity:
            return None, 'no_sale_capacity_bound'
        for receipt in report['unit_receipts']:
            if receipt['exists'] and receipt['effective_action'] == ['DROP']:
                deposited = {
                    item: qty - receipt['inventory_after'].get(item, 0)
                    for item, qty in receipt['inventory_before'].items()
                    if qty > receipt['inventory_after'].get(item, 0)
                }
                if deposited:
                    deliveries.append({'step': step, 'actor': receipt['actor'],
                                       'quantities': deposited})
        mechanics._decay_plants(farm, step)
    return {'farm': farm, 'private': private, 'deliveries': deliveries,
            'max_stock_without_sales': max_stock}, None


def _delivery_reset(mechanics, farm, private, capacity):
    """The delivery/reset portion of official EOD, with no hidden RNG input.

    Equality of the complete pre-refresh tiles is checked separately. Thus
    identical future daily refresh/weather cannot conceal a task difference.
    """
    farm, private = deepcopy(farm), deepcopy(private)
    mechanics._drop_inventories_to_shed(private, capacity)
    farm['farmer'] = list(mechanics._default_spawn(len(farm['tiles'])))
    farm['hands'] = []
    farm['hires_today'] = 0
    private['inventories'] = [{}]
    return farm, private


def propose_delivery(mechanics, observation, selected_action, route,
                     configuration=None, *, audit, branch_steps=()):
    """Return at most one complete same-day proposal and an explicit report.

    ``route`` must be the caller's actual committed route after its existing
    producer selection. This function neither selects nor invokes a parent.
    The caller commits patches only with an action actually returned, exposes
    those patches to SELL, and owns recovery after an interrupted action.
    """
    cfg = dict(configuration or {})
    now = int(observation['step'])
    per_day = int(cfg.get('turnsPerDay', 24))
    last = int(cfg.get('episodeSteps', 720)) - 2
    close = (now // per_day + 1) * per_day - 1
    report = {'step': now, 'day_close': close, 'admitted': False,
              'reason': None, 'candidates': []}

    def decline(reason):
        report['reason'] = reason
        return None, report

    farm = observation['farms'][observation['player']]
    if (per_day != 24 or len(farm['tiles']) != 10
            or int(cfg.get('shedCapacity', 100)) != 100):
        return decline('unsupported_configuration')
    if close > last or close >= len(route):
        return decline('no_executed_day_end')
    if any(now < int(step) <= close for step in branch_steps):
        return decline('branch_in_window')
    if close - now < 2:
        return decline('insufficient_remaining_slots')
    rows = [deepcopy(selected_action)] + [deepcopy(route[t])
                                         for t in range(now + 1, close + 1)]
    if any(order and order[0] != 'SELL'
           for row in rows for order in row.get('market', [])):
        return decline('economic_obligation_in_window')
    account = account_ordered_yield(mechanics, observation, selected_action,
                                   cfg, audit=audit)
    report['structural_duplicates'] = account['structural_duplicates']
    structural = {tuple(group['position'])
                  for group in account['structural_duplicates']}
    empty = [actor for group in account['depletion_groups']
             if tuple(group['position']) in structural
             for actor in group['depleted_actors']]
    if not empty:
        return decline('no_ordered_depletion')
    baseline, error = _project(mechanics, observation, cfg, rows, now)
    if error:
        return decline(error)
    baseline_reset = _delivery_reset(mechanics, baseline['farm'],
                                     baseline['private'], 100)
    for actor in empty:
        candidate_report = {'actor': actor}
        report['candidates'].append(candidate_report)
        # Only existing hired workers can rejoin by expiring at day close.
        if actor == 0 or unit(route[now], actor) != unit(selected_action, actor):
            candidate_report['reason'] = 'not_unchanged_hired_worker'
            continue
        original = [list(unit(row, actor)) for row in rows]
        if any(not a or a[0] not in {*MOVES, *TASKS, 'PASS'}
               for a in original[1:]):
            candidate_report['reason'] = 'input_or_other_task_in_suffix'
            continue
        origin = tuple(farm['hands'][actor - 1])
        remaining = original[1:]
        while remaining and remaining[-1] == ['PASS']:
            remaining.pop()
        position = origin
        mandatory = []
        for offset, action in enumerate(remaining):
            if action[0] in TASKS:
                mandatory.append({'position': list(position), 'action': action,
                                  'offset': offset})
            position = move(position, action, 10)
        delivery_paths = []
        for shed in mechanics._shed_access_tiles(10):
            replacement = remaining + path(position, shed) + [['DROP']]
            if len(replacement) <= len(rows):
                delivery_paths.append((len(replacement), tuple(shed), replacement))
        if not delivery_paths:
            candidate_report['reason'] = 'no_delivery_path_fits'
            continue
        _, shed, replacement = min(delivery_paths, key=lambda item: item[:2])
        # The optional delivery is checked at the last actual market turn.
        # Keep extra slack before DROP, where it cannot imply an earlier
        # unguarded arrival to the SELL consumer.
        replacement = (replacement[:-1]
                       + [['PASS']] * (len(rows) - len(replacement))
                       + [['DROP']])
        drop_step = close
        changed = deepcopy(rows)
        for row, action in zip(changed, replacement):
            set_unit(row, actor, action)
        # Do not credit hypothetical future sales for space at the proposed
        # DROP. Movement/tasks can be certified without executing that optional
        # delivery. The runtime checks it from actual state at drop_step.
        set_unit(changed[drop_step - now], actor, ['PASS'])
        projected, error = _project(mechanics, observation, cfg, changed, now)
        if error:
            candidate_report['reason'] = error
            continue
        # Preserve all production tiles and all other workers' inventories.
        if projected['farm']['tiles'] != baseline['farm']['tiles']:
            candidate_report['reason'] = 'production_tiles_differ'
            continue
        if any(a != b for i, (a, b) in enumerate(zip(
                baseline['private']['inventories'],
                projected['private']['inventories'])) if i != actor):
            candidate_report['reason'] = 'other_worker_inventory_differ'
            continue
        if _delivery_reset(mechanics, projected['farm'],
                           projected['private'], 100) != baseline_reset:
            candidate_report['reason'] = 'delivery_reset_differ'
            continue
        delivered = dict(projected['private']['inventories'][actor])
        produce = {item: qty for item, qty in delivered.items()
                   if item not in ('WHEAT', 'FERTILIZER') and qty > 0}
        if not produce:
            candidate_report['reason'] = 'no_produce_delivered'
            continue
        plan = {'step': now, 'end': close + 1, 'worker': actor,
                'origin': list(origin), 'goal': list(shed),
                'original': original, 'replacement': replacement,
                'mandatory_tasks': mandatory, 'drop_step': drop_step,
                'delivered': delivered,
                'delivery_conditional_on_actual_capacity': True,
                'rejoin': 'official_day_end_worker_expiry',
                'max_stock_without_sales': max(
                    baseline['max_stock_without_sales'],
                    projected['max_stock_without_sales'])}
        candidate_report.update(reason='production_conserved_conditional_delivery',
                                drop_step=drop_step, delivered=delivered)
        report.update(admitted=True, reason='production_conserved_conditional_delivery',
                      market_receipt_gain=None)
        return plan, report
    return decline('no_supported_productive_rejoin')


def guard_delivery(mechanics, observation, selected, actor, configuration=None):
    """Allow the optional DROP only from current observed capacity/stock.

    No market receipt is assumed. Both complete current own-unit stages must
    fit, and deterministic EOD delivery/reset must preserve the same products.
    """
    cfg = dict(configuration or {})
    now = int(observation['step'])
    if (now + 1) % int(cfg.get('turnsPerDay', 24)) != 0:
        return False, {'reason': 'not_executed_day_close'}
    if now > int(cfg.get('episodeSteps', 720)) - 2:
        return False, {'reason': 'not_executed_day_close'}
    if any(order and order[0] != 'SELL' for order in selected.get('market', [])):
        return False, {'reason': 'economic_obligation_at_delivery'}
    reference = deepcopy(selected)
    set_unit(reference, actor, ['PASS'])
    proposed = deepcopy(reference)
    set_unit(proposed, actor, ['DROP'])
    control, error = _project(mechanics, observation, cfg, [reference], now,
                              require_capacity=True)
    if error:
        return False, {'reason': error}
    changed, error = _project(mechanics, observation, cfg, [proposed], now,
                              require_capacity=True)
    if error:
        return False, {'reason': error}
    capacity = int(cfg.get('shedCapacity', 100))
    if (_delivery_reset(mechanics, control['farm'], control['private'], capacity)
            != _delivery_reset(mechanics, changed['farm'], changed['private'], capacity)):
        return False, {'reason': 'delivery_changes_product_conservation'}
    deliveries = [entry for entry in changed['deliveries'] if entry['actor'] == actor]
    if not deliveries:
        return False, {'reason': 'empty_or_invalid_delivery'}
    return True, {'reason': 'observed_capacity_and_products_preserved',
                  'deliveries': deliveries,
                  'max_stock_without_sales': changed['max_stock_without_sales']}
