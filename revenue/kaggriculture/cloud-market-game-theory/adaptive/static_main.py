# SPDX-License-Identifier: Apache-2.0
"""Preserved static weak-dominance ablation, without evaluator metadata."""
from pathlib import Path
import sys

_RUNTIME = None
_AGENT = None


def agent(observation, configuration=None):
    global _RUNTIME, _AGENT
    cfg = dict(configuration or {})
    if _RUNTIME is None:
        # Direct raw compilation may expose only the code filename.
        # Keep the normal build_agent __raw_path__ contract as well.
        source = (globals().get('__file__') or cfg.get('__raw_path__')
                  or agent.__code__.co_filename)
        here = Path(source).resolve().parent
        sys.path.insert(0, str(here))
        import importlib.util
        spec = importlib.util.spec_from_file_location('adaptive_static_runtime', here/'runtime.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _RUNTIME = module
    # Use the existing clock contract before reset, history, or recourse sees it.
    # Missing step is not turn zero: official observations may carry day/hour.
    obs = dict(observation)
    obs['step'] = _RUNTIME.sale.absolute_step(obs, cfg)
    if _AGENT is None or obs['step'] == 0:
        _AGENT = _RUNTIME.Agent('static')
    return _AGENT.act(obs, cfg)
