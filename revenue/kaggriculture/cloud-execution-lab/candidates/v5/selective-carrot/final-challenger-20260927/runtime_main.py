# SPDX-License-Identifier: Apache-2.0
"""Isolated selected-unit and final-market composition over exact V4."""
import baseline_main as baseline
import full_production_context
from delivery_choice import DeliveryChoice

_FACTORY = baseline._new_instance
_CHOICE = None
_INSTANCE = None
_PREWARMED = None


def _factory(root, features):
    global _CHOICE, _PREWARMED
    from mechanics import market_price
    from scheduler import post_units
    # Initialize before the first action timer is armed. The official raw
    # loader may charge import time to that callback, so keep this work small.
    if _PREWARMED is not None:
        warm_root, warm_features, instance = _PREWARMED
        _PREWARMED = None
        if warm_root != root or warm_features != features:
            instance = _FACTORY(root, features)
    else:
        instance = _FACTORY(root, features)
    if _CHOICE is None:
        _CHOICE = DeliveryChoice(market_price, max_active=12)
    selected_transform = instance.transform_selected
    final_market = instance._early_capital_selected

    def units(obs, cfg, selected):
        changed = _CHOICE.units(obs, cfg, selected, instance.controller.cur)
        return selected_transform(obs, cfg, changed)

    def market(obs, cfg, selected):
        out = final_market(obs, cfg, selected)
        if instance.diagnostics.get('status') == 'completed':
            farm, private = post_units(obs, out, cfg)
            post = dict(obs, farms=list(obs['farms']), private=private)
            post['farms'][obs['player']] = farm
            out = _CHOICE.market(obs, cfg, out, instance.controller.R[instance.controller.cur],
                                 instance.controller.cur, post)
            instance.diagnostics['crop_choice'] = dict(_CHOICE.report)
        return out

    instance.transform_selected = units
    instance._early_capital_selected = market
    return instance


baseline._new_instance = _factory


def _prewarm_first_controller():
    global _PREWARMED
    import json
    from pathlib import Path
    root = Path(baseline.__file__).resolve().parent
    features = json.loads((root / 'TITAN-CONFIG.json').read_text())
    # Call the unwrapped constructor: _factory is the action-time wrapper and
    # the first real observation must still install its ordinary adapters.
    instance = _FACTORY(root, features)
    instance._initialize()
    _PREWARMED = (root, features, instance)


_prewarm_first_controller()


def agent(observation, configuration=None):
    global _CHOICE, _INSTANCE
    step = observation.get('step')
    if step is None:
        step = (int(observation.get('day', 0)) * int((configuration or {}).get('turnsPerDay', 24))
                + int(observation.get('hour', 0)))
    step = int(step)
    observation = dict(observation, step=step)
    if step == 0:
        _CHOICE = None
    import full_production_context
    full_production_context.configuration = dict(configuration or {})
    returned = baseline.agent(observation, configuration)
    _INSTANCE = baseline._INSTANCE
    if _CHOICE is not None:
        _CHOICE.commit(observation, returned)
    from wf1_current_adapter import apply_wf1_current
    return apply_wf1_current(
        observation, returned, configuration, enabled=True)
