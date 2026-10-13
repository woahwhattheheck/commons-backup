# SPDX-License-Identifier: Apache-2.0
"""Opt-in agent entry point. Existing parent files are imported, not rewritten."""
import importlib.util
from pathlib import Path
import sys
from sell_backend import make_optimizer

HERE = Path(__file__).resolve().parent
SELL = HERE.parent / 'cloud-titan-composition/vendor/sell'
_instance = None

def load_scheduler(path=SELL):
    path = Path(path).resolve()
    sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location('t06_incumbent_sell', path / 'scheduler.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def agent(observation, configuration=None):
    global _instance
    if _instance is None or int(observation.get('step', 0)) == 0:
        module = load_scheduler()
        module.optimize_lot = make_optimizer(module)
        _instance = module.SellScheduler()
    return _instance.act(observation, configuration)
