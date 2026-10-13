# SPDX-License-Identifier: Apache-2.0
"""Isolated selected-unit and final-market composition over exact V4."""
import baseline_main as baseline
from selective_carrot import CropChoice

_FACTORY = baseline._new_instance
_CHOICE = None
_INSTANCE = None


def _factory(root, features):
    global _CHOICE
    from mechanics import market_price
    from scheduler import post_units
    instance = _FACTORY(root, features)
    if _CHOICE is None:
        _CHOICE = CropChoice(market_price)
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


def agent(observation, configuration=None):
    global _CHOICE, _INSTANCE
    step = observation.get('step', observation.get('day', 0)*24+observation.get('hour', 0))
    if step == 0:
        _CHOICE = None
    returned = baseline.agent(observation, configuration)
    _INSTANCE = baseline._INSTANCE
    if _CHOICE is not None:
        _CHOICE.commit(observation, returned)
    return returned
