"""Build observation-only T10 entrypoints using the existing licensed wrappers.

No network IO. Requires the verified sourcepack and previously prepared Arlene /
Apex runtime (next-panel/prepare.py). Generated absolute paths are local execution
artifacts; rerun this builder when moving the working directory.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ARLENE_SHA = '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4'
ENGINE_REF = '28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c'
PARENT_REF = '8329e78768906dc6e75ca3712e1690adc1ab2148'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare(sourcepack: Path, runtime: Path):
    sourcepack, runtime = sourcepack.resolve(), runtime.resolve()
    manifest = json.loads((sourcepack/'SOURCE_MANIFEST.json').read_text())
    if manifest['commons_ref'] != PARENT_REF or manifest['engine_ref'] != ENGINE_REF:
        raise ValueError('sourcepack pins differ')
    for name, evidence in manifest['files'].items():
        path = (sourcepack/name).resolve()
        if not path.is_relative_to(sourcepack):
            raise ValueError('manifest path outside sourcepack')
        data = path.read_bytes()
        if len(data) != evidence['bytes'] or hashlib.sha256(data).hexdigest() != evidence['sha256']:
            raise ValueError(f'sourcepack mismatch: {name}')
    base = sourcepack/'commons/revenue/kaggriculture'
    panel = base/'cloud-frontier-policy/next-panel'
    arlene = panel/'vendor/arlene.py'
    if hashlib.sha256(arlene.read_bytes()).hexdigest() != ARLENE_SHA:
        raise ValueError('Arlene source changed')
    ev = load(base/'cloud-eval/evaluate.py', 't10_prepare_eval')
    ev.get_engine(sourcepack/'engine')
    pack = load(base/'cloud-pack/pack.py', 't10_prepare_pack')
    runtime.mkdir(parents=True, exist_ok=True)
    for required in ('arlene-adapter.py', 'apex-adapter.py', 'manifest.json'):
        if not (runtime/required).is_file():
            raise FileNotFoundError('Run next-panel/prepare.py for the baseline runtime first')
    for mode in ('reserve', 'timed'):
        entry = runtime/f't10-{mode}.py'
        entry.write_text(
            'import sys as _sys\nimport importlib.util as _util\n'
            f'_sys.path.insert(0, {str(HERE)!r})\n'
            'from labor_capital import HiringAgent as _HiringAgent\n'
            '_state = None\n'
            'def _module(path, name):\n'
            '    spec = _util.spec_from_file_location(name, path)\n'
            '    module = _util.module_from_spec(spec)\n'
            '    _sys.modules[name] = module\n'
            '    spec.loader.exec_module(module)\n'
            '    return module\n'
            'def agent(observation, configuration=None):\n'
            '    global _state\n'
            '    if _state is None or observation.get("step", 0) == 0:\n'
            f'        parent = _module({str(arlene)!r}, "t10_intact_arlene")\n'
            f'        ev = _module({str(base/"cloud-eval/evaluate.py")!r}, "t10_native_eval")\n'
            f'        engine, _ = ev.get_engine({str(sourcepack/"engine")!r})\n'
            f'        _state = _HiringAgent(parent.Agent(), engine, mode={mode!r}, configuration=configuration)\n'
            '    return _state.act(observation)\n')
        adapter = runtime/f't10-{mode}-adapter.py'
        pack.write_adapter(adapter, entry)
        prefix = ('import sys\n'+f'sys.path.insert(0, {str(panel)!r})\n'
                  'from offline import restrict\nrestrict()\n')
        adapter.write_text(prefix+adapter.read_text())
    evidence = {'sourcepack_ref': PARENT_REF, 'engine_ref': ENGINE_REF,
                'arlene_sha256': ARLENE_SHA, 'runtime_kind': 'existing offline file-agent wrapper',
                'local_source': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(HERE.glob('*.py'))},
                'entrypoints': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(runtime.glob('t10-*.py'))}}
    (runtime/'T10-MANIFEST.json').write_text(json.dumps(evidence, indent=2)+'\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sourcepack', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.sourcepack, args.runtime), indent=2))
