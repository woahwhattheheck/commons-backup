# SPDX-License-Identifier: Apache-2.0
"""Experimental E17 public-regime variant over the existing SELL scheduler.

The canonical scheduler remains untouched.  This module supplies an explicit
run-only entrypoint so matched games can compare the hard eight-turn baseline
with bounded repeated-event memory before any default is changed.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _load('e17_base_scheduler', HERE / 'scheduler.py')
regime = _load('e17_public_regime_history', HERE / 'seller_regime_history.py')


def _product_of(tile):
    if not isinstance(tile, dict):
        return None
    if tile.get('kind') == 'PLANT':
        return tile.get('crop')
    return base.m.ANIMALS.get(tile.get('animal'), {}).get('product')


class RegimeSellScheduler(base.SellScheduler):
    """Run-only E17 candidate; baseline `scheduler.agent` is unchanged."""

    def __init__(self, mode='candidate'):
        super().__init__(mode)
        self.regime_history = regime.PublicRegimeHistory()
        self.previous_action = None
        self._regime_configuration = {}

    def _visible_supply(self, obs, item):
        rival = obs['farms'][1 - int(obs['player'])]
        total = 0
        for row in rival['tiles']:
            for tile in row:
                if _product_of(tile) == item:
                    total += max(0, int(tile.get('yield_units', 0)))
        return total

    def observe(self, obs):
        # Seed the public production baseline on the opening observation. Without
        # this, the first step0->1 mix change is silently adopted as the baseline
        # and bypasses the existing persistence/reset confirmation rule.
        self.regime_history.observe(
            self.previous,
            obs,
            self.previous_action if self.previous is not None else None,
            self._regime_configuration,
            products=base.PRODUCTS,
            product_of=_product_of,
            absorption=base.absorption,
        )
        # Retain baseline diagnostics/history for direct comparison and to avoid
        # changing any unrelated scheduler behavior.
        super().observe(obs)

    def rival_supply(self, obs, item):
        signal = self.regime_history.signal(
            int(obs['step']), item, visible=self._visible_supply(obs, item)
        )
        self.diagnostics.setdefault('regime_supply', {})[item] = signal
        return signal['stress']

    def act(self, obs, configuration=None):
        self._regime_configuration = dict(configuration or {})
        output = super().act(obs, configuration)
        self.previous_action = copy.deepcopy(output)
        return output


_INSTANCE = None
_LAST_STEP = None


def agent(obs, configuration=None):
    global _INSTANCE, _LAST_STEP
    step = int(obs.get('step', 0))
    if _INSTANCE is None or (_LAST_STEP is not None and step < _LAST_STEP):
        _INSTANCE = RegimeSellScheduler()
    output = _INSTANCE.act(obs, configuration)
    _LAST_STEP = step
    return output
