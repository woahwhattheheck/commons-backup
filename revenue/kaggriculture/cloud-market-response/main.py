# SPDX-License-Identifier: MIT
"""Lazy file-agent entrypoint; the official raw loader does not define __file__."""
import importlib.util as _util
from pathlib import Path as _Path
import sys as _sys

_instance = None

def agent(observation, configuration=None):
    global _instance
    configuration = configuration or {}
    if observation.get('step') is None:
        step = int(observation['day']) * int(configuration.get('turnsPerDay', 24)) + int(observation['hour'])
        observation = dict(observation, step=step)
    if _instance is None or int(observation['step']) == 0:
        # The pinned official contract supplies this before invoking agent,
        # AFTER raw-source execution. Direct module imports supply __file__.
        raw_path = configuration.get('__raw_path__') or globals().get('__file__')
        root = _Path(raw_path).resolve().parent if raw_path else _Path.cwd()
        source = root/'policy.py'
        if not source.is_file():
            source = root/'revenue/kaggriculture/cloud-market-response/policy.py'
        spec = _util.spec_from_file_location('t12_exported_policy', source)
        module = _util.module_from_spec(spec)
        _sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _instance = module.ResponsePolicy()
    return _instance.act(observation, configuration)
