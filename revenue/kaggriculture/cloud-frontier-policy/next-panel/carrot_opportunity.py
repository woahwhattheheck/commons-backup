"""LARK / Commons, Apache-2.0. Isolated Arlene v14 carrot-route gate.

All route tapes, execution and persistent state remain Arlene's. This is a
current-price allocation heuristic, not a forecast or exact realized profit.
At the parent's existing turn360 decision, require positive marked-to-current-
price incremental tail value in addition to the original carrot-price floor.
Only already visible prices are read; no future shops, seeds or opponent orders.
"""
_CARROT_OPPORTUNITY_PARENT = agent
_CARROT_OPPORTUNITY_FEATURE = _feature
_CARROT_OPPORTUNITY_LAST = {}


def _feature(obs, name):
    if name == 'px_CARROT':
        prices = obs['market']['prices']
        # Exact YARN_CARROT minus YARN planned tail quantities from turn360.
        # Fertilizer: seven fewer sold and eight more bought. Seed costs:
        # 26 carrot seeds at20, minus one wheat seed at10. Ignore two fewer
        # planned hires, whose savings depend on within-day successful hiring.
        value = (84 * prices.get('CARROT', 0)
                 - 54 * prices.get('MILK', 0)
                 - 44 * prices.get('WHEAT', 0)
                 - 4 * prices.get('STRAWBERRY', 0)
                 - 15 * prices.get('FERTILIZER', 0) - 510)
        _CARROT_OPPORTUNITY_LAST.update(step=obs.get('step'),
                                       current_price_tail_value=value,
                                       allow_carrot=value > 0)
        if value <= 0:
            return -1
    return _CARROT_OPPORTUNITY_FEATURE(obs, name)


def lark_carrot_opportunity_entrypoint(observation):
    return _CARROT_OPPORTUNITY_PARENT(observation)
