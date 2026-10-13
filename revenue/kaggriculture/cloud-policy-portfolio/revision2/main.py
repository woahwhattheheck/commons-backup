# SPDX-License-Identifier: Apache-2.0
"""Relocatable research entry; default selected SELL remains at ../selected.py."""
_agent = None


def agent(observation, configuration=None):
    global _agent
    if _agent is None:
        from pathlib import Path
        import importlib.util
        import sys
        raw = globals().get('__file__') or (configuration or {}).get('__raw_path__')
        if not raw:
            raise ValueError('Supply the raw source path')
        here = Path(raw).resolve().parent
        sys.path.insert(0, str(here))
        spec = importlib.util.spec_from_file_location('t14_revision2_policy', here/'policy.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _agent = module.make_agent()
    return _agent(observation, configuration)
