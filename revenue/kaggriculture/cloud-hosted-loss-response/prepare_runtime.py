# SPDX-License-Identifier: Apache-2.0
"""Prepare process-isolated controls using the existing pack and offline guard."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(runtime, source_root):
    runtime, source_root = Path(runtime).resolve(), Path(source_root).resolve()
    vendor = load('t13_builder', HERE / 'build.py').verify_sources()
    runtime.mkdir(parents=True, exist_ok=False)
    panel = source_root / 'cloud-frontier-policy/next-panel'
    pack = load('t13_existing_pack', source_root / 'cloud-pack/pack.py')
    shutil.copytree(panel / 'vendor/apex', runtime / 'apex',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.so'))
    command = ['g++', '-O3', '-std=c++17', '-Wall', '-Wextra', '-pedantic',
               '-shared', '-fPIC', '-Isource/include', '-o', 'agent.so',
               'source/policy.cpp', 'submission_bridge.cpp']
    result = subprocess.run(command, cwd=runtime / 'apex', capture_output=True,
                            text=True, check=True)
    (runtime / 'compile.txt').write_text(result.stdout + result.stderr)
    frozen = runtime / 'frozen-import.py'
    frozen.write_text('import importlib.util\nimport sys\n_policy = None\n'
        'def agent(obs, config=None):\n    global _policy\n'
        '    if _policy is None or int(obs.get("step", 0)) == 0:\n'
        f'        path = {str(vendor)!r}\n'
        '        sys.path.insert(0, path)\n'
        '        spec = importlib.util.spec_from_file_location("t13_frozen", path + "/scheduler.py")\n'
        '        module = importlib.util.module_from_spec(spec)\n'
        '        spec.loader.exec_module(module)\n'
        '        _policy = module.SellScheduler()\n'
        '    return _policy.act(obs, config)\n')
    targets = {'seed': HERE / 'seed_main.py', 'weed': HERE / 'main.py',
               'sell': frozen, 'frozen': frozen,
               'arlene': vendor / 'reference/next-panel/vendor/arlene.py',
               'apex': runtime / 'apex/main.py'}
    for name, path in targets.items():
        adapter = runtime / (name + '-adapter.py')
        pack.write_adapter(adapter, path)
        adapter.write_text('import sys\n' + f'sys.path.insert(0, {str(panel)!r})\n'
                           'from offline import restrict\nrestrict()\n' + adapter.read_text())
    manifest = {'source_freeze': json.loads((HERE / 'SOURCE-FREEZE.json').read_text()),
                'compile_command': command,
                'compiler': subprocess.check_output(['g++', '--version'], text=True),
                'execution': 'Existing cloud-eval and unchanged offline syscall guard.',
                'files': {str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(runtime.rglob('*')) if p.is_file()}}
    (runtime / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=Path('/tmp/t13-runtime'))
    parser.add_argument('--source-root', type=Path, default=HERE.parent)
    args = parser.parse_args()
    print(json.dumps(prepare(args.runtime, args.source_root), indent=2))
