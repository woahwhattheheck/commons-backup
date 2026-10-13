# SPDX-License-Identifier: Apache-2.0
"""Read-only pinned full-interpreter support; rejects missing files before import."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import sys

PINS = {
    'main.py': '4a8cf7bcda1f0fea231a144692cb84a779a9e73e',
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d',
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def authenticate(root):
    root = Path(root).resolve()
    for path, expected in PINS.items():
        if not (root / path).is_file() or blob((root / path).read_bytes()) != expected:
            raise ValueError('input authentication failed: ' + path)
    # Authenticate the checked release's own manifest, then all 109 entries.
    # SOURCE.json is the 110th member and is pinned independently below.
    raw = (root / 'SOURCE.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2':
        raise ValueError('manifest authentication failed')
    manifest = json.loads(raw)
    for path, metadata in manifest['runtime'].items():
        if not (root / path).is_file():
            raise ValueError('runtime authentication failed: ' + path)
        data = (root / path).read_bytes()
        if len(data) != metadata['bytes'] or hashlib.sha256(data).hexdigest() != metadata['sha256']:
            raise ValueError('runtime authentication failed: ' + path)
    return root


def engine(root):
    root = authenticate(root)
    loader = load(root / 'checks/reference/evaluator/loader.py', 'priceseed_loader')
    original, _ = loader.get_engine(root / 'checks/reference/engine')
    return original, loader.Struct


def initial(original, Struct, seed=17, overrides=None):
    cfg = Struct({key: value.get('default') if isinstance(value, dict) else value
                  for key, value in original.specification['configuration'].items()})
    cfg.update(overrides or {})
    cfg.seed = seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    original.interpreter(state, env)
    return state, env


def advance(original, state, env, actions, step):
    for seat in range(2):
        state[seat].observation.step = step
        state[seat].action = copy.deepcopy(actions[seat])
    original.interpreter(state, env)
    return state
