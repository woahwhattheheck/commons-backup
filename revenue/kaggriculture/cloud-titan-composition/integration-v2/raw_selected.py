# SPDX-License-Identifier: MIT
"""Lazy raw-file entrypoint for the unchanged selected SELL package."""
_FUNCTION = None


def agent(observation, configuration=None):
    global _FUNCTION
    if _FUNCTION is None:
        import importlib.util
        from pathlib import Path
        import sys
        config = configuration or {}
        raw_path = globals().get('__file__') or config.get('__raw_path__')
        if not raw_path:
            raise RuntimeError('File loader must supply __file__ or __raw_path__')
        directory = Path(raw_path).resolve().parent/'vendor'/'sell'
        sys.path.insert(0,str(directory))
        spec = importlib.util.spec_from_file_location('t08_raw_frozen_sell',directory/'scheduler.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _FUNCTION = module.agent
    return _FUNCTION(observation, configuration)
