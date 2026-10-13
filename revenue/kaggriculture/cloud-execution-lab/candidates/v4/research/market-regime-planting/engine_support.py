# SPDX-License-Identifier: Apache-2.0
"""Offline access to already-present, hash-verified official engine bytes."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path

PINS = {
 'checks/reference/engine/kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
 'checks/reference/engine/kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
 'checks/reference/engine/utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
 'checks/reference/evaluator/loader.py': 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e',
}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_engine(root):
    root = Path(root).resolve()
    for relative, expected in PINS.items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'official source drift: {relative}')
    loader = load_module(root / 'checks/reference/evaluator/loader.py', '_seed_regime_reference_loader')
    engine, hashes = loader.get_engine(root / 'checks/reference/engine')
    return engine, loader, hashes


def new_game(engine, loader, seed, overrides=None):
    cfg = loader.Struct({k: v.get('default') if isinstance(v, dict) else v
                         for k, v in engine.specification['configuration'].items()})
    cfg.update(overrides or {})
    cfg.seed = int(seed)
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    for s in state:
        s.observation.step = 0
    return state, env, cfg
