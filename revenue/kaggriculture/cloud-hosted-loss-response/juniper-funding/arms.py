# SPDX-License-Identifier: Apache-2.0
"""Three named arms using the existing T13 factory and one frozen SELL actor."""
from pathlib import Path
import sys

_INSTANCES = {}


def make_agent(mode='funded'):
    if mode not in ('funded', 'legacy', 'sell'):
        raise ValueError('mode must be funded, legacy, or sell')
    root = Path(make_agent.__code__.co_filename).resolve().parent.parent
    for directory in (root, root.parent / 'cloud-integration-differentials'):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from seed_main import make_agent as build
    from seed_funding import select_seed_queue
    return build(root, enabled=mode != 'sell',
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


def sell(observation, configuration=None):
    return _act('sell', observation, configuration)
