# SPDX-License-Identifier: Apache-2.0
"""Seed recovery over the SAME HAZEL capital actor and its selected route.

The existing current-quote route chooser remains an optional research policy.
No route, seller, economic forecast or default policy is changed by this join.
"""
from pathlib import Path
import importlib.util
import sys

_INSTANCES = {}


def make_agent(mode='funded'):
    if mode not in ('funded', 'legacy', 'capital'):
        raise ValueError('mode must be funded, legacy, or capital')
    root = Path(make_agent.__code__.co_filename).resolve().parent.parent
    for directory in (root, root.parent / 'cloud-integration-differentials'):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from seed_main import make_agent as build
    from seed_funding import select_seed_queue
    path = root.parent / 'cloud-capital-bundles' / 'entry.py'
    spec = importlib.util.spec_from_file_location('_juniper_capital_entry', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policy = module.make_agent()
    return build(root, enabled=mode != 'capital', policy=policy,
                 controller=policy.scheduler.controller,
                 seed_queue_selector=select_seed_queue if mode == 'funded' else None)


def _act(mode, observation, configuration):
    step = observation.get('step')
    if step is None:
        step = int(observation['day']) * int((configuration or {}).get('turnsPerDay', 24)) + int(observation['hour'])
    if mode not in _INSTANCES or int(step) == 0:
        _INSTANCES[mode] = make_agent(mode)
    return _INSTANCES[mode](observation, configuration)


def agent(observation, configuration=None):
    return _act('funded', observation, configuration)


def legacy(observation, configuration=None):
    return _act('legacy', observation, configuration)


def capital(observation, configuration=None):
    return _act('capital', observation, configuration)
