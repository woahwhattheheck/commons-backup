"""LARK observed-stock sale overlay, Apache-2.0; production stays with Kaito.

No new farm route selection, no parent reconstruction, no seed access.
"""
_FRONTIER_PARENT = agent
_FINISHED = ('MILK', 'WOOL', 'EGG', 'STRAWBERRY', 'MELON', 'TOMATO', 'CARROT')
_FRONTIER_STATE = {}


def sell_finished(obs, action, configuration=None):
    """Preserve parent capital/feed slots; use spare slots for observed goods."""
    action = _copy_action(action)
    projected = _projected_shed(obs, action)
    for item in _FINISHED:
        projected[item] = max(0, projected.get(item, 0) - _v17_pickup_reserve(action, item))
    market = [list(o) for o in action.get('market', [])]
    handled = set()
    for order in market:
        if len(order) >= 3 and order[0] == 'SELL' and order[1] in _FINISHED:
            item = order[1]
            order[2] = projected.get(item, 0) if item not in handled else 0
            handled.add(item)
    sales = [['SELL', item, projected.get(item, 0)] for item in _FINISHED
             if item not in handled and projected.get(item, 0) > 0]
    sales.sort(key=lambda o: _order_score(obs, configuration, o), reverse=True)
    capacity = int(_get(configuration, 'maxMarketOrdersPerTurn', 10))
    action['market'] = market + sales[:max(0, capacity-len(market))]
    return action


def agent(obs, configuration=None):
    seat, step = _seat(obs), int(_get(obs, 'step', 0))
    state = _FRONTIER_STATE.get(seat)
    if state is None or step <= state['last_step']:
        state = {'last_step': -1, 'changed_market_turns': 0}
        _FRONTIER_STATE[seat] = state
    # Exactly one call to the actual parent entrypoint. Its persistent route
    # and weed-repair state advance normally; worker actions are not edited.
    parent_action = _FRONTIER_PARENT(obs, configuration)
    from v19_terminal import clone_distance
    distance = clone_distance(obs)
    state['sale_regime'] = 'competing_supply' if distance <= 2 else 'parent_schedule'
    result = sell_finished(obs, parent_action, configuration) if distance <= 2 else parent_action
    state['last_step'] = step
    state['changed_market_turns'] += result['market'] != parent_action.get('market', [])
    state['route'] = _V43_POLICY.states[seat]['route']
    return result


def _kaggle_submission_entrypoint(obs, configuration=None):
    return agent(obs, configuration)
