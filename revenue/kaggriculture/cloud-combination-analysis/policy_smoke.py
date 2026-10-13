# SPDX-License-Identifier: Apache-2.0
"""Exercise timing transparency on the existing intact Arlene source, no games.

The frames here are explicit synthetic observations, not reached game states.
No seeds are selected, no interpreter game is run, and no policy is promoted.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform

from execution_timing import TimedFactory

EXPECTED_ARLENE = '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4'


def observation(products, step, seat):
    farm = {'tiles': [[None for _ in range(10)] for _ in range(10)],
            'farmer': [4, 4], 'hands': [[4, 4], [4, 4]], 'money': 10000}
    return {'step': step, 'day': step // 24, 'hour': step % 24, 'player': seat,
            'farms': [deepcopy(farm), deepcopy(farm)],
            'private': {'seeds': {'CARROT': 10, 'TOMATO': 10, 'STRAWBERRY': 10, 'MELON': 10},
                        'inventories': [{}, {}, {}], 'shed': {'CARROT': 3}},
            'market': {'prices': {p: 50 for p in products},
                       'inventory': {p: 100 for p in products}},
            'town': {'unlocked_shops': []}}


def run(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_ARLENE:
        raise ValueError('Smoke requires the documented intact Arlene bytes')
    spec = importlib.util.spec_from_file_location('timing_smoke_arlene', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = []
    for seat in (0, 1):
        direct = module.Agent()
        factory = TimedFactory(lambda: module.Agent().act)
        actor = factory()
        for step in (0, 1, 22, 23, 100, 718):
            obs = observation(module.PRODUCTS, step, seat)
            control_obs, observed_obs = deepcopy(obs), deepcopy(obs)
            expected = direct.act(control_obs)
            actual = actor(observed_obs)
            if actual != expected or observed_obs != control_obs:
                raise AssertionError(f'Timing changed policy behavior at {seat}/{step}')
            rows.append({'seat': seat, 'step': step, 'action': actual,
                         'action_equal': True, 'input_after_equal': True})
        rows.append({'seat': seat, 'timing': actor.timings()})
    return {'scope': 'synthetic_observation_callable_compatibility_not_games',
            'python': platform.python_version(), 'arlene_sha256': digest,
            'cases': 12, 'differences': 0, 'games': 0, 'seeds': [], 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arlene', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = run(args.arlene)
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, sort_keys=True))
