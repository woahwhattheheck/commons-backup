"""LARK harvest rescue, Apache-2.0; append to the frozen native main.

Use an impossible FEED/CARE/COLLECT or PASS to harvest already visible yield.
No movement, route, planting, purchase or market-order edit. Parent is called
once per turn and retains its persistent state. This is next-iteration code.
"""
_HARVEST_PARENT = lark_frontier_submission_entrypoint
_HARVEST_RESCUE_STATE = {}


def lark_harvest_rescue_entrypoint(obs, configuration=None):
    action = _HARVEST_PARENT(obs, configuration)
    seat, step = int(obs.get('player', 0)), int(obs.get('step', 0))
    state = _HARVEST_RESCUE_STATE.setdefault(seat, {'last_step':-1,'repairs':0})
    if step <= state['last_step']:
        state.update(last_step=-1, repairs=0)
    farm = obs['farms'][seat]
    positions = [farm['farmer']] + list(farm['hands'])
    inventories = obs['private']['inventories']
    units = [action['farmer']] + list(action.get('hands', []))
    claimed, repaired = set(), []
    for index, (position, original) in enumerate(zip(positions, units)):
        x, y = position
        key = (x, y)
        tile = farm['tiles'][y][x]
        if not isinstance(tile, dict) or tile.get('yield_units', 0) <= 0 or key in claimed:
            continue
        op = original[0] if original else 'PASS'
        if op == 'HARVEST':
            claimed.add(key)
            continue
        free = (op == 'PASS'
                or (op == 'FEED' and (tile.get('fed_today') or inventories[index].get('WHEAT', 0) <= 0))
                or (op == 'CARE' and tile.get('cared_today'))
                or (op == 'COLLECT_FERTILIZER' and not tile.get('fertilizer_available')))
        if free:
            units[index] = ['HARVEST']
            claimed.add(key)
            repaired.append(index)
    state['last_step'] = step
    state['repairs'] += len(repaired)
    state['last_repaired_units'] = repaired
    if repaired:
        action = dict(action)
        action['farmer'], action['hands'] = units[0], units[1:]
    return action
