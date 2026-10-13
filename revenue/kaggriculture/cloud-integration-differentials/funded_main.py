# SPDX-License-Identifier: Apache-2.0
"""Opt-in CEDAR funding selection over the existing integrated TITAN agent.

Run from a repository checkout with cloud-execution-lab beside this directory.
This is a research variant, not a replacement for the frozen selected archive.
"""
from pathlib import Path
import sys

_INSTANCE = None


def make_agent(production=None, *, funded=True, seed=True, committed=True,
               sell=True, horizon=8):
    """Reuse one producer; funded=False is the unchanged integrated control.

    The selector only handles proposals the original route-demand stage allows.
    It does not create seeds, change worker routes, or infer rival inventories.
    """
    # Match integrated_main's raw-file loader contract: __file__ is not required.
    root = Path(make_agent.__code__.co_filename).resolve().parent
    for directory in (root, root.parent / 'cloud-execution-lab'):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from integrated_selected import make_agent as build
    from seed_funding import select_seed_queue
    return build(
        production, seed=seed, committed=committed, sell=sell, horizon=horizon,
        seed_queue_selector=select_seed_queue if funded else None)


def agent(observation, configuration=None):
    global _INSTANCE
    configuration = dict(configuration or {})
    step = observation.get('step')
    if step is None:
        step = int(observation['day']) * int(configuration.get('turnsPerDay', 24)) + int(observation['hour'])
    if _INSTANCE is None or step == 0:
        _INSTANCE = make_agent()
    return _INSTANCE.act(observation, configuration)
