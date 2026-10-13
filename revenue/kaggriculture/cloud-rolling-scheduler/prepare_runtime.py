"""Prepare real offline T03/Arlene/Apex adapters using existing licensed sources.

No downloads, account actions or policy submission. Apex is compiled before the
existing source pack's network/exec guard is enabled in each actor process.
"""
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


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare(output, engine_dir):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    engine_dir = Path(engine_dir).resolve()
    ev = load(ROOT / 'cloud-eval/evaluate.py', 't03_existing_evaluator')
    engine_sources = ev.verify_sources(engine_dir)
    pack = load(ROOT / 'cloud-pack/pack.py', 't03_existing_pack')
    vendor = ROOT / 'cloud-frontier-policy/next-panel/vendor'
    source_files = {name: HERE / name for name in ('scheduler.py', 'policy.py')}
    source_files['oracle.py'] = ROOT / 'cloud-service-value/oracle.py'
    source_files['arlene.py'] = vendor / 'arlene.py'
    for name, source in source_files.items():
        shutil.copyfile(source, output / name)
    shutil.copytree(vendor / 'apex', output / 'apex', dirs_exist_ok=True)
    command = ['g++', '-O3', '-std=c++17', '-Wall', '-Wextra', '-pedantic', '-shared', '-fPIC',
               '-Isource/include', '-o', 'agent.so', 'source/policy.cpp', 'submission_bridge.cpp']
    if not (output / 'apex/agent.so').exists():
        done = subprocess.run(command, cwd=output / 'apex', capture_output=True, text=True, check=True)
        (output / 'compile.txt').write_text(done.stdout + done.stderr)
    loader = ROOT / '20260907-offline-agent/evaluate.py'
    for name, maximum in (('candidate', 2), ('translated_control', 0)):
        main = output / (name + '.py')
        main.write_text('from pathlib import Path\nimport sys, importlib.util, json\n'
                        f'HERE=Path({str(output)!r})\nsys.path.insert(0,str(HERE))\n'
                        'import arlene, oracle\nfrom policy import RollingAgent\n'
                        f'spec=importlib.util.spec_from_file_location("t03_loader",{str(loader)!r})\n'
                        'module=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n'
                        f'engine,_=module.get_engine(Path({str(engine_dir)!r}))\n'
                        f'controller=RollingAgent(arlene,engine,oracle,max_candidates={maximum})\n'
                        'def agent(observation,configuration):\n    action=controller.act(observation,configuration)\n    if int(observation["step"])==718:\n        Path("t03-events.json").write_text(json.dumps(controller.events))\n    return action\n')
    adapters = {}
    for name, main in (('candidate', output/'candidate.py'), ('translated_control',output/'translated_control.py'),
                       ('arlene', output/'arlene.py'), ('apex',output/'apex/main.py')):
        path = output/(name+'-adapter.py')
        pack.write_adapter(path, main)
        path.write_text('import sys\n'+f'sys.path.insert(0,{str(ROOT / "cloud-frontier-policy/next-panel")!r})\n'
                        'from offline import restrict\nrestrict()\n'+path.read_text())
        adapters[name] = str(path)
    receipt = {'adapters': adapters, 'engine_sources': engine_sources, 'compile_command': command,
               'source_sha256': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name,path in source_files.items()},
               'runtime_sha256': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in output.rglob('*') if p.is_file() and '__pycache__' not in str(p)},
               'network': 'existing offline seccomp guard before policy import; no new network or execution permission'}
    (output/'runtime-manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--engine-dir',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(prepare(a.output,a.engine_dir),indent=2))
