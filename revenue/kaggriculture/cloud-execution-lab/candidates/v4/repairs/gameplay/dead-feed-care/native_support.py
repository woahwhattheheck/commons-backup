# SPDX-License-Identifier: Apache-2.0
"""Offline input authentication and full official-engine setup for W2 native gates."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

MANIFEST_SHA = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
BASE_CONFIG_SEMANTIC_SHA = '9b1d49a6da7ab7706bd0c749aebfa5f1b715b461c792a167e4fbb16f5d592788'
HELPER_SHA = 'cf03a048688fd615aa40e4c0b5b018f4f630888f65e909faa8eadafff2cf9f75'
STARVATION_HELPER_SHA = 'a03938c7b1064f24aac52fb5a7e97a63083b1c8ffe8fa420c0fbfe5f95f9d73e'
FAST_HELPER_SHA = '80f6c82b735199227c7caabea10107867a3cb3ca7f0af7a6af7073dfa79b22c0'
BASE_RUNTIME_SHA = 'da391af2dbdec0f6e4a25749ed539cdd39578ace8861c0e225b5fbfef90d75a8'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def authenticate(package, manifest, *, runtime_sha=BASE_RUNTIME_SHA, enabled=False,
                 composed=False, starvation=False, fast_tape=False):
    package, manifest = Path(package), Path(manifest)
    if starvation and not composed:
        raise ValueError('starvation activation requires the existing W2 composition')
    if sha(manifest) != MANIFEST_SHA:
        raise ValueError('wrong checked-release manifest')
    data = json.loads(manifest.read_text())['runtime']
    config = json.loads((package/'TITAN-CONFIG.json').read_text())
    baseline_config = dict(config)
    if enabled:
        if baseline_config.pop('r04_dead_feed_care', None) is not True:
            raise ValueError('enabled native configuration is not actually enabled')
    elif 'r04_dead_feed_care' in baseline_config:
        raise ValueError('disabled baseline configuration must remain byte-exact')
    for name, record in data.items():
        path = package/name
        expected = record['sha256']
        if name == 'titan_runtime.py':
            expected = runtime_sha
        if name == 'TITAN-CONFIG.json' and enabled:
            if hashlib.sha256(json.dumps(baseline_config, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != BASE_CONFIG_SEMANTIC_SHA:
                raise ValueError('configuration changed beyond W2')
        elif sha(path) != expected:
            raise ValueError('input authentication failed: '+name)
    if sha(package/'SOURCE.json') != MANIFEST_SHA:
        raise ValueError('archive SOURCE manifest differs')
    expected_names = set(data) | {'SOURCE.json'}
    if fast_tape:
        if sha(package/'r04_fast_tape_clone.py') != FAST_HELPER_SHA:
            raise ValueError('fast-tape helper differs from authenticated source')
        expected_names.add('r04_fast_tape_clone.py')
    if composed:
        if sha(package/'r04_dead_feed_care.py') != HELPER_SHA:
            raise ValueError('W2 source differs from authenticated dead-feed-care helper')
        expected_names.add('r04_dead_feed_care.py')
    if starvation:
        if sha(package/'r04_uncared_eod_feed_skip.py') != STARVATION_HELPER_SHA:
            raise ValueError('guarded starvation helper differs from authenticated source')
        expected_names.add('r04_uncared_eod_feed_skip.py')
    actual_names = {p.relative_to(package).as_posix() for p in package.rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    if actual_names != expected_names:
        raise ValueError('package member set differs: '+str(sorted(actual_names ^ expected_names)))
    return {'authenticated_release_members': len(data), 'runtime_sha256': runtime_sha,
            'manifest_sha256': MANIFEST_SHA, 'helper_sha256': HELPER_SHA if composed else None,
            'starvation_helper_sha256': STARVATION_HELPER_SHA if starvation else None,
            'fast_tape_helper_sha256': FAST_HELPER_SHA if fast_tape else None,
            'enabled': enabled, 'composed': composed, 'starvation': starvation, 'fast_tape': fast_tape}


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_engine(package):
    package = Path(package)
    loader = load_file('_w2_official_loader', package/'checks/reference/evaluator/loader.py')
    engine, hashes = loader.get_engine(package/'checks/reference/engine')
    return engine, loader.Struct, hashes


def new_world(engine, Struct, *, seed=17, step=0):
    cfg = Struct({key: value.get('default') if isinstance(value, dict) else value
                  for key, value in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    for s in state:
        s.observation.step = step
        s.observation.day, s.observation.hour = divmod(step, 24)
    return state, env


def load_native(package):
    package = Path(package).resolve()
    sys.path.insert(0, str(package))
    main = load_file('_w2_native_main', package/'main.py')
    return main
