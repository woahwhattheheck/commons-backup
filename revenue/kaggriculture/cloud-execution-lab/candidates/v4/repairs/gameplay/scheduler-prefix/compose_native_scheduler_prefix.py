#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose existing V4 prefix repairs and bind the native frozen consumer.

Source-only: exact inputs, existing sibling repair modules, fresh output only.
No legacy apply_v4, production writes, feature changes, or game-strength claim.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import types

SOURCE_BLOBS = {
    'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
    'frozen_selected.py': 'fc7baf5c179818a55037f6a61d92984d81d1a21c',
}
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
DEPENDENCIES = {
    'materialize_scheduler_prefix.py': 'f36e9120ea07c861a7eca5821a5306c6dbfa4613',
    'act_sale_prefix.py': '57b3e5cf284a91ac7dbacafde45da499e628428d',
}
SCHEDULER_AFTER = '9ae62209e956fee0f76b3dbe87dfef3eb6296731'
NATIVE_HELPERS = '''# V4-NATIVE-PREFIX: a read-only call-local view; never replace controller.R.
def _v4_native_prefix_action(action, limit):
    result = dict(action)
    raw = action.get('market', [])
    result['market'] = raw[:limit] if isinstance(raw, list) else []
    return result


class _V4NativePrefixTape:
    __slots__ = ('_route', '_limit')

    def __init__(self, route, limit):
        self._route, self._limit = route, limit

    def __len__(self):
        return len(self._route)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [_v4_native_prefix_action(row, self._limit)
                    for row in self._route[index]]
        return _v4_native_prefix_action(self._route[index], self._limit)


'''
PRELUDE = '''        # Bound every native helper to executable raw slots before planning.
        # Terminal settlement retains its exact existing path and input bytes.
        _v4_raw_suffix = []
        if now != last:
            _v4_limit = max(1, int(config.get('maxMarketOrdersPerTurn', 10)))
            config['maxMarketOrdersPerTurn'] = _v4_limit
            _v4_raw_market = base.get('market', [])
            if isinstance(_v4_raw_market, list):
                _v4_raw_suffix = _v4_raw_market[_v4_limit:]
            base = _v4_native_prefix_action(base, _v4_limit)
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def bind(data: bytes, expected: str, label: str) -> None:
    if not isinstance(data, bytes) or git_blob(data) != expected:
        raise ValueError(label + ': exact source identity mismatch')


def _replace(text: str, old: str, new: str, expected: int = 1) -> str:
    if text.count(old) != expected:
        raise ValueError('native transform anchor drift: ' + old.strip()[:100])
    return text.replace(old, new)


def repair_frozen(source: bytes) -> bytes:
    bind(source, SOURCE_BLOBS['frozen_selected.py'], 'frozen_selected.py')
    text = source.decode('utf-8')
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == 'FrozenSelected']
    if len(classes) != 1 or classes[0].decorator_list:
        raise ValueError('native class shape drift')
    methods = [n for n in classes[0].body if isinstance(n, ast.FunctionDef)
               and n.name == 'transform']
    if len(methods) != 1 or methods[0].decorator_list:
        raise ValueError('native method shape drift')
    node = methods[0]
    lines = text.splitlines(keepends=True)
    method = ''.join(lines[node.lineno - 1:node.end_lineno])
    method = _replace(method, '        self.observe(obs)\n', PRELUDE + '        self.observe(obs)\n')
    method = _replace(method,
        '        route=self.controller.R[self.controller.cur]\n',
        '        route=_V4NativePrefixTape(self.controller.R[self.controller.cur], _v4_limit)\n',
        expected=2)
    method = _replace(method,
        '        self.previous=seller_public_observation(obs)\n        return out\n',
        '        self.previous=seller_public_observation(obs)\n'
        '        # Pending/plans above account only for actually executable rows.\n'
        "        out['market'].extend(copy.deepcopy(_v4_raw_suffix))\n"
        '        return out\n')
    output = (''.join(lines[:node.lineno - 1]) + method
              + ''.join(lines[node.end_lineno:]))
    output = _replace(output, 'class FrozenSelected(SellScheduler):\n',
                      NATIVE_HELPERS + 'class FrozenSelected(SellScheduler):\n')
    compile(output, '<v4-native-prefix>', 'exec')
    return output.encode('utf-8')


def _dependency(directory: Path, name: str):
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('repair dependency must be a regular non-symlink file: ' + name)
    data = path.read_bytes()
    bind(data, DEPENDENCIES[name], name)
    # Execute exactly the verified bytes, not a second filesystem read.
    module = types.ModuleType('_ridge_' + path.stem)
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def compose(scheduler: bytes, frozen: bytes, engine: bytes,
            dependency_dir: Path | None = None) -> tuple[dict[str, bytes], dict]:
    bind(scheduler, SOURCE_BLOBS['scheduler.py'], 'scheduler.py')
    bind(frozen, SOURCE_BLOBS['frozen_selected.py'], 'frozen_selected.py')
    bind(engine, ENGINE_BLOB, 'official engine')
    directory = Path(dependency_dir) if dependency_dir is not None else Path(__file__).parent
    projection = _dependency(directory, 'materialize_scheduler_prefix.py')
    act = _dependency(directory, 'act_sale_prefix.py')
    projected = projection.materialize(scheduler, engine)
    combined, act_receipt = act.rewrite_source(projected.decode('utf-8'))
    combined = combined.encode('utf-8')
    bind(combined, SCHEDULER_AFTER, 'composed scheduler')
    native = repair_frozen(frozen)
    outputs = {'scheduler.py': combined, 'frozen_selected.py': native}
    receipt = {
        'operation': 'ASTRA-RIDGE-NATIVE-SCHEDULER-PREFIX-COMPOSITION',
        'input_blobs': SOURCE_BLOBS, 'engine_blob': ENGINE_BLOB,
        'dependency_blobs': DEPENDENCIES,
        'projection_intermediate_blob': git_blob(projected),
        'act_receipt': act_receipt,
        'outputs': {name: {'git_blob': git_blob(data), 'bytes': len(data),
                           'sha256': hashlib.sha256(data).hexdigest()}
                    for name, data in outputs.items()},
        'legacy_prefix3': {
            'source_blob': 'da1b6fb571e79ba7dab54c8d816e45afb934e4d2',
            'candidate_blob': '4dcf25f0a1a68f6842b71c6cb58ee878c06f6a08',
            'disposition': 'DO_NOT_APPLY_TO_CURRENT_SOURCE',
            'reason': 'E14 removed current receipt pre-debit; the two surviving '
                      'cash/receipt consumers are handled by the modern projection donor.',
        },
        'native_scope': 'nonterminal FrozenSelected.transform and its call-local market/tape views',
        'terminal_changed': False, 'controller_tape_mutated': False,
        'game_economics_run': False, 'production_activation': False,
    }
    return outputs, receipt


def write_bundle(lab: Path, engine_path: Path, output: Path,
                 dependency_dir: Path | None = None) -> dict:
    paths = {name: lab / name for name in SOURCE_BLOBS}
    paths['engine'] = engine_path
    for name, path in paths.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError('bound input must be a regular non-symlink file: ' + name)
    inputs = {name: path.read_bytes() for name, path in paths.items()}
    outputs, receipt = compose(inputs['scheduler.py'], inputs['frozen_selected.py'],
                               inputs['engine'], dependency_dir)
    for name, path in paths.items():
        if path.read_bytes() != inputs[name]:
            raise ValueError('input changed during composition: ' + name)
    # mkdir is exclusive. An existing directory, file, or symlink is never used.
    output.mkdir(parents=False, exist_ok=False)
    outputs['COMPOSITION.json'] = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    for name, data in outputs.items():
        with (output / name).open('xb') as stream:
            stream.write(data)
    for name, path in paths.items():
        if path.read_bytes() != inputs[name]:
            raise ValueError('input changed during publication: ' + name)
    for name, data in outputs.items():
        if (output / name).read_bytes() != data:
            raise ValueError('output readback mismatch: ' + name)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True,
                        help='Fresh validation directory; never the production root')
    args = parser.parse_args()
    try:
        report = write_bundle(args.lab, args.engine, args.output)
    except (OSError, ValueError, SyntaxError) as exc:
        parser.exit(2, f'composition refused: {exc}\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
