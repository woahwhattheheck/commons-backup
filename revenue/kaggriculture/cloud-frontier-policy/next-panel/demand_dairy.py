"""LARK demand-gated dairy continuation, Apache-2.0, derived from Arlene v14.

Keep the complete main dairy schedule when two already visible milk-consuming
shops provide sustained demand. Otherwise retain the parent's milk-glut exit.
Only that route predicate changes; no averaging, seed/future-shop access or
market/action overlay. The parent retains all persistent route/service state.
"""
_DEMAND_DAIRY_PARENT = agent
_DEMAND_DAIRY_FEATURE = _feature
_MILK_SHOPS = {'PIZZA_SHOP', 'SMOOTHIE_SHOP', 'ICE_CREAM_SHOP'}
_DEMAND_DAIRY_OBSERVED = {}


def _feature(obs, name):
    if name == 'inv_MILK':
        count = sum(shop in _MILK_SHOPS for shop in obs.get('town', {}).get('unlocked_shops', []))
        _DEMAND_DAIRY_OBSERVED.update(step=obs.get('step'), milk_shops=count,
                                     inventory=obs['market']['inventory'].get('MILK', 0),
                                     retained_dairy=count >= 2)
        if count >= 2:
            return -1
    return _DEMAND_DAIRY_FEATURE(obs, name)


def lark_demand_dairy_entrypoint(observation):
    return _DEMAND_DAIRY_PARENT(observation)
