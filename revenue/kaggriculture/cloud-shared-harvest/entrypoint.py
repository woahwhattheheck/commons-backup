# SPDX-License-Identifier: Apache-2.0
"""Explicit experimental consumer of one immutable canonical TITAN package.

Place ENTRYPOINT-INPUTS.json beside this file with absolute package_root and
audit_path values. A normal league actor gets a fresh process per match. The
existing canonical constructor and one guarded TitanAgent.act are retained.
"""
import importlib.util
import json
from pathlib import Path
import sys
import time

_INSTANCE = None
_RUNTIME = None
_INPUTS = None


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agent(observation, configuration=None):
    global _INSTANCE, _RUNTIME, _INPUTS
    started = time.perf_counter()
    cfg = dict(configuration or {})
    if _INPUTS is None:
        here = Path(__file__).resolve().parent
        _INPUTS = json.loads((here / 'ENTRYPOINT-INPUTS.json').read_text())
        for path in (str(here), _INPUTS['package_root'],
                     _INPUTS.get('helper_root', str(here))):
            if path not in sys.path:
                sys.path.insert(0, path)
    step = observation.get('step')
    if step is None:
        step = int(observation['day']) * int(cfg.get('turnsPerDay', 24)) + int(observation['hour'])
    if _INSTANCE is None or int(step) == 0:
        root = Path(_INPUTS['package_root'])
        canonical = _load('_shared_harvest_canonical_main', root / 'main.py')
        features = json.loads((root / 'TITAN-CONFIG.json').read_text())
        _INSTANCE = canonical._new_instance(root, features)
        audit = _load('_shared_harvest_exact_audit', Path(_INPUTS['audit_path']))
        from scheduler import m, parent
        from runtime import attach
        _RUNTIME = attach(_INSTANCE, m, audit.duplicate_harvest_targets,
                          branch_steps=[row[0] for row in parent.DECISIONS])
    return _INSTANCE.act(observation, cfg, entry_started=started)
