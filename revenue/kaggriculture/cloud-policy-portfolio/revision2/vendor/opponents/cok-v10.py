"""T07 cok-v10: one instance per actor/match; no source edits."""
import importlib.util as _util
from pathlib import Path as _Path
_runner = None

def agent(observation, configuration=None):
    global _runner
    if _runner is None:
        root = _Path(agent.__code__.co_filename).resolve().parent
        spec = _util.spec_from_file_location('t07_public_bank', root / 'bank.py')
        bank = _util.module_from_spec(spec)
        spec.loader.exec_module(bank)
        _runner = bank.make_agent(root, 'cok-v10')
    return _runner(observation, configuration or {})
