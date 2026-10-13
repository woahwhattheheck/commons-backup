# SPDX-License-Identifier: MIT
"""Native file-loader entry, valid without __file__ in Kaggle's exec globals."""
import importlib.util
from pathlib import Path
import sys

_module = None


def agent(observation, configuration=None):
    global _module
    if _module is None:
        raw = (configuration or {}).get('__raw_path__') or globals().get('__file__')
        if not raw:
            raise ValueError('Native loader must provide __raw_path__')
        here = Path(raw).resolve().parent
        spec = importlib.util.spec_from_file_location('_osprey_composition', here / 'composition.py')
        _module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = _module
        spec.loader.exec_module(_module)
    return _module.agent(observation, configuration)
