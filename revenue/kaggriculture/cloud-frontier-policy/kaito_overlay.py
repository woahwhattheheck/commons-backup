"""LARK additions, Apache-2.0. Concatenated after the unchanged Igor source.

Preserves one production route. Replaces replay-counter sale predictions with
observed finished-goods liquidation; never reads an environment seed.
"""
_FRONTIER_MODE = 'immediate'
_FRONTIER_STATE = {}
_PARENT_AGENT = agent
_FINISHED = ('MILK', 'WOOL', 'EGG', 'STRAWBERRY', 'MELON', 'TOMATO', 'CARROT')
_ROUTES = {'10c4s_3q': _ACTIONS_10C4S_3Q, '8c6s_3q': _ACTIONS_8C6S_3Q,
           '6c8s_3q': _ACTIONS_6C8S_3Q,
           '6c12s_4q_first_yarn': _ACTIONS_6C12S_4Q_FIRST_YARN,
           '6c12s_4q_second_yarn': _ACTIONS_6C12S_4Q_SECOND_YARN}
_PREFIX = {(a, b): next((i for i, (x, y) in enumerate(zip(ra, rb)) if x != y), min(len(ra), len(rb)))
           for a, ra in _ROUTES.items() for b, rb in _ROUTES.items()}
_ROUTE_STATE = {}


def _kawa_actions(obs):
    """Commit to a route suffix once the issued prefixes diverge."""
    seat, step = _seat(obs), int(_get(obs, 'step', 0))
    state = _ROUTE_STATE.get(seat)
    if state is None or step < state['last_step'] or step == 0:
        state = {'last_step': -1, 'route': '8c6s_3q', 'blocked_switches': 0}
        _ROUTE_STATE[seat] = state
    desired = _kawa_route_label(obs)
    if _PREFIX[state['route'], desired] >= step:
        state['route'] = desired
    elif state['route'] != desired:
        state['blocked_switches'] += 1
    state['last_step'] = step
    return _ROUTES[state['route']]


def frontier_agent(obs, configuration=None):
    seat = _seat(obs)
    step = int(_get(obs, 'step', 0))
    state = _FRONTIER_STATE.get(seat)
    if state is None or step <= state['last_step']:
        state = {'last_step': -1, 'route': None, 'sales_turns': 0,
                 'previous_prices': {}, 'observed_cash': 0}
        _FRONTIER_STATE[seat] = state
    state['last_step'] = step
    # The parent's route changes only from observed shops/layout. Retain its
    # weed transactions, storage evacuation and complete worker schedule.
    action = _V43_POLICY(obs, configuration)
    state['route'] = _V43_POLICY.states[seat]['route']
    if _FRONTIER_MODE == 'parent':
        return _PARENT_AGENT(obs)
    # Feed wheat and fertilizer retain the production plan's own quantities.
    # Project only known same-turn deposits; subtract known worker pickups.
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
    # Daily route indices depend on every planned HIRE. Never truncate a
    # parent order to make room for an opportunistic sale.
    capacity = int(_get(configuration, 'maxMarketOrdersPerTurn', 10))
    action['market'] = market + sales[:max(0, capacity-len(market))]
    state['sales_turns'] += bool(sales)
    state['previous_prices'] = dict(_get(_get(obs, 'market', {}), 'prices', {}))
    state['observed_cash'] = _get(_farm(obs, seat), 'money', 0)
    return _align_hands(action, obs)


def agent(obs, configuration=None):
    return frontier_agent(obs, configuration)


def _kaggle_submission_entrypoint(obs, configuration=None):
    return agent(obs, configuration)
