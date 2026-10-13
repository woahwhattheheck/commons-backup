#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
_parent = None
_adapter = None


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_loaded():
    global _parent, _adapter
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if _parent is None:
        _parent = _load('wf1_v5_parent', ROOT / 'main.py')
    if _adapter is None:
        _adapter = _load('wf1_v5_adapter', ROOT / 'wf1_current_adapter.py')


def agent(observation, configuration=None):
    _ensure_loaded()
    parent_action = _parent.agent(observation, configuration)
    return _adapter.apply_wf1_current(
        observation, parent_action, configuration, enabled=True)
