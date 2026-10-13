"""LARK experimental feed rescue, Apache-2.0. Append to frozen main.py.

One edit: replace a provably ineffective stationary action with FEED when
the observed animal is unfed and the same worker already holds wheat.
No new movements, purchases, route selection, sale quantities or timing.
"""
_RESCUE_PARENT = lark_frontier_submission_entrypoint
_RESCUE_STATE = {}


def lark_feed_rescue_entrypoint(obs, configuration=None):
    action = _RESCUE_PARENT(obs, configuration)
    seat = int(obs.get('player', 0))
    step = int(obs.get('step', 0))
    state = _RESCUE_STATE.setdefault(seat, {'last_step':-1, 'repairs':0})
    if step <= state['last_step']:
        state.update(last_step=-1, repairs=0)
    farm = obs['farms'][seat]
    inventories = obs['private']['inventories']
    positions = [farm['farmer']] + list(farm['hands'])
    units = [action['farmer']] + list(action.get('hands', []))
    fed = set()
    repaired = []
    for index, (position, original) in enumerate(zip(positions, units)):
        x, y = position
        tile = farm['tiles'][y][x]
        if not isinstance(tile, dict) or not tile.get('animal'):
            continue
        key = (x, y)
        wheat = inventories[index].get('WHEAT', 0)
        if tile.get('fed_today') or key in fed or wheat <= 0:
            continue
        op = original[0] if original else 'PASS'
        if op == 'FEED':
            fed.add(key)
            continue
        free = (op == 'PASS'
                or (op == 'HARVEST' and tile.get('yield_units', 0) <= 0)
                or (op == 'CARE' and tile.get('cared_today'))
                or (op == 'COLLECT_FERTILIZER' and not tile.get('fertilizer_available')))
        if free:
            units[index] = ['FEED']
            fed.add(key)
            repaired.append(index)
    state['last_step'] = step
    state['repairs'] += len(repaired)
    state['last_repaired_units'] = repaired
    if repaired:
        action = dict(action)
        action['farmer'], action['hands'] = units[0], units[1:]
    return action
