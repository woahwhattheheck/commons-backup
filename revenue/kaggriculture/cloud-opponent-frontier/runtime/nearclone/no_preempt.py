"""Exploratory ablation: unchanged Barnyard V7 with its preemption flag disabled."""
from pathlib import Path
import importlib.util

_policy = None


def agent(obs, configuration=None):
    global _policy
    if _policy is None:
        # The pinned file loader sets __raw_path__ in configuration, not __file__.
        raw_path = (configuration or {}).get('__raw_path__') or globals().get('__file__')
        if not raw_path:
            raise ValueError('Supply the file-loader configuration or import this module normally')
        source = Path(raw_path).resolve().parents[1] / 'barnyard-v7/main.py'
        spec = importlib.util.spec_from_file_location('t07_barnyard_no_preempt', source)
        _policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_policy)
        _policy._PREEMPT_ENABLED = False
    return _policy.agent(obs)
