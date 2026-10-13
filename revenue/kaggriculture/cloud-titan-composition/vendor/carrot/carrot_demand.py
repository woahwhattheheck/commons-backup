"""LARK / Commons Apache-2.0: visible carrot-demand route experiment.

Reuse Arlene v14's entire controller and compatible YARN_CARROT schedule.
At its existing turn360 decision, an already unlocked FARMERS_MARKET can
trigger the carrot allocation even before the parent's price42 threshold.
All original price-triggered switches remain available. Current shop existence
is only a demand signal; it is not a prediction of future shops or prices.
"""
_CARROT_DEMAND_PARENT = agent
_CARROT_DEMAND_FEATURE = _feature


def _feature(obs, name):
    value = _CARROT_DEMAND_FEATURE(obs, name)
    if name == 'px_CARROT':
        shops = obs.get('town', {}).get('unlocked_shops') or []
        if 'FARMERS_MARKET' in shops:
            return max(42, value)
    return value


def lark_carrot_demand_entrypoint(observation):
    return _CARROT_DEMAND_PARENT(observation)
