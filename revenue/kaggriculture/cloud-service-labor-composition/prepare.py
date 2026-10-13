# SPDX-License-Identifier: MIT
"""Prepare an offline runtime from pinned existing sources; performs no downloads."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PINS = {
    'cloud-labor-capital/labor_capital.py': 'd75ad4eff579bb137f9ca5644cbca13c368d3327c83e31240dd765cd0f1564e3',
    'cloud-service-value/policy.py': '1ac10c1a54085849d0ff1378aa596ed6f79ec77d3e569316a37dca26c19e4aeb',
    'cloud-service-value/oracle.py': '61c9898aa5dd25f537647ecba3005c588dfe684110763944c71b12f85672674a',
    'cloud-frontier-policy/next-panel/vendor/arlene.py': '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4',
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(runtime: Path, engine_dir: Path):
    runtime = runtime.resolve()
    if runtime.exists():
        raise FileExistsError(f'Use a new runtime directory: {runtime}')
    for relative, expected in PINS.items():
        if digest(ROOT / relative) != expected:
            raise ValueError(f'Pinned source changed: {relative}')
    evaluator = load(ROOT / 'cloud-eval/evaluate.py', 'keel_prepare_eval')
    evaluator.verify_sources(engine_dir)
    runtime.mkdir(parents=True)
    shutil.copytree(engine_dir, runtime / 'engine')
    shutil.copy2(ROOT / '20260907-offline-agent/evaluate.py', runtime / 'engine_loader.py')
    shutil.copy2(HERE / 'composition.py', runtime / 'composition.py')
    for source, target in (
        ('cloud-labor-capital/labor_capital.py', 'labor_capital.py'),
        ('cloud-service-value/policy.py', 'service_policy.py'),
        ('cloud-service-value/oracle.py', 'oracle.py'),
        ('cloud-frontier-policy/next-panel/vendor/arlene.py', 'arlene.py'),
    ):
        shutil.copy2(ROOT / source, runtime / target)
    vendor = ROOT / 'cloud-frontier-policy/next-panel/vendor/apex'
    shutil.copytree(vendor, runtime / 'apex')
    command = ['g++', '-O3', '-std=c++17', '-Wall', '-Wextra', '-pedantic',
               '-shared', '-fPIC', '-Isource/include', '-o', 'agent.so',
               'source/policy.cpp', 'submission_bridge.cpp']
    result = subprocess.run(command, cwd=runtime / 'apex', capture_output=True,
                            text=True, check=True)
    (runtime / 'compile.txt').write_text(result.stdout + result.stderr)
    shutil.copytree(ROOT / 'cloud-titan-composition/vendor/sell', runtime / 'sell')
    shutil.copy2(ROOT / 'cloud-titan-composition/vendor/base/LICENSE', runtime / 'LICENSE-ARLENE')
    shutil.copy2(ROOT / 'cloud-titan-composition/vendor/base/NOTICE.txt', runtime / 'NOTICE-UPSTREAM.txt')
    shutil.copytree(ROOT / 'cloud-pack', runtime / 'loading')
    shutil.copy2(ROOT / 'cloud-frontier-policy/next-panel/offline.py', runtime / 'offline.py')
    (runtime / 'boot.py').write_text('''from pathlib import Path
import importlib.util
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from composition import Composition
import arlene, labor_capital, service_policy

def create(service, labor, configuration=None):
    spec = importlib.util.spec_from_file_location("keel_runtime_loader", HERE / "engine_loader.py")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    engine, _ = loader.get_engine(HERE / "engine")
    return Composition(arlene, labor_capital, service_policy, engine, configuration,
                       service=service, labor=labor)
''')
    for name, service, labor in [('parent', False, False), ('service', True, False),
                                  ('labor', False, True), ('both', True, True)]:
        (runtime / f'{name}_main.py').write_text(f'''from pathlib import Path
import sys
_policy = None

def agent(observation, configuration=None):
    global _policy
    sys.path.insert(0, str(Path(agent.__code__.co_filename).resolve().parent))
    from boot import create
    if _policy is None or observation.get('step') == 0:
        _policy = create({service!r}, {labor!r}, configuration)
    return _policy.act(observation, configuration)
''')
    (runtime / 'sell_main.py').write_text("""from pathlib import Path
import sys
_runner = None

def agent(observation, configuration=None):
    global _runner
    if _runner is None:
        sys.path.insert(0, str(Path(agent.__code__.co_filename).resolve().parent / 'sell'))
        from scheduler import agent as run
        _runner = run
    return _runner(observation, configuration)
""")
    pack = load(runtime / 'loading/pack.py', 'keel_existing_pack')
    for name in ['parent', 'service', 'labor', 'both', 'arlene', 'apex', 'sell']:
        main = (runtime / f'{name}_main.py' if name in ('parent','service','labor','both')
                else runtime / 'arlene.py' if name == 'arlene'
                else runtime / 'apex/main.py' if name == 'apex'
                else runtime / 'sell_main.py')
        target = runtime / f'{name}_adapter.py'
        pack.write_adapter(target, main)
        text = target.read_text()
        guard = ('from pathlib import Path as _Path\nimport sys as _sys\n'
                 '_sys.path.insert(0, str(_Path(__file__).resolve().parent))\n'
                 'import offline as _offline\n_offline.restrict()\n')
        target.write_text(guard + text)
    manifest = {'pins': PINS, 'engine': evaluator.verify_sources(engine_dir),
                'compiler_command': command,
                'compiler_version': subprocess.check_output(['g++','--version'],text=True),
                'files': {str(p.relative_to(runtime)):digest(p) for p in sorted(runtime.rglob('*'))
                          if p.is_file() and '__pycache__' not in p.parts},
                'policy_scope':'T04/T10 composition research; selected TITAN SELL unchanged'}
    (runtime / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--engine-dir', required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.runtime, args.engine_dir)
    print(json.dumps({'prepared':str(args.runtime), 'files':len(result['files'])}))
