# SPDX-License-Identifier: Apache-2.0
"""Source-bound projection-copy experiment for the one canonical TITAN V4.

Only two existing function spans are changed. No policy, action, key, timer,
market admission or economic objective is rewritten. Outputs are source-only.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

HELPER_SHA256 = 'f5916d47e01d37d848047930b397003632b98042a53dfc6c027dd85c7ef1c87e'
PINS = {
    'represented_shed_event': {
        # Native fc7baf5c, then the same function after UNITFLOW e1127c4a.
        '5f3b2f66cf77ce177d951aa0dec3acff5d9cb4c5530f5ece27ab1f733373e9b7',
        '81e8710927a6af2f1306ab6acfcf181963451aef62182a044d32d5b5f9119b1c',
    },
    '_project_post_unit_private': {
        '2c0e9143e7e05fddcd267059fa060c5c424f0abac3c8a6fd76f34915cbec1196',
    },
}
REPLACEMENTS = {
    'represented_shed_event': (
        ("    f,p=copy.deepcopy(farm),copy.deepcopy(private)",
         "    from projection_clone import clone_projection as _clone_projection\n"
         "    f,p=_clone_projection(farm),_clone_projection(private)"),
    ),
    '_project_post_unit_private': (
        ("        farm = deepcopy(farms[player])",
         "        from projection_clone import clone_projection as _clone_projection\n"
         "        farm = _clone_projection(farms[player])"),
        ("        private = deepcopy(observation.get('private'))",
         "        private = _clone_projection(observation.get('private'))"),
    ),
}


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def span(source: str, name: str) -> tuple[int, int, str]:
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise ValueError(f'{name}: missing, duplicate or decorated source boundary')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, source[start:end]


def compose_source(source: str, name: str) -> str:
    start, end, original = span(source, name)
    if hashlib.sha256(original.encode()).hexdigest() not in PINS[name]:
        raise ValueError(f'{name}: unrecognized method; do not override source pins')
    changed = original
    for old, new in REPLACEMENTS[name]:
        if changed.count(old) != 1:
            raise ValueError(f'{name}: missing or ambiguous copy seam')
        changed = changed.replace(old, new, 1)
    result = source[:start] + changed + source[end:]
    compile(result, name, 'exec')
    return result


def compose_sources(frozen: str, capital: str) -> tuple[str, str]:
    return (compose_source(frozen, 'represented_shed_event'),
            compose_source(capital, '_project_post_unit_private'))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path,
                        help='New source-only directory, never an existing runtime')
    args = parser.parse_args()
    helper = Path(__file__).with_name('projection_clone.py').read_bytes()
    if hashlib.sha256(helper).hexdigest() != HELPER_SHA256:
        raise SystemExit('projection_clone.py does not match the tested helper pin')
    names = ('frozen_selected.py', 'early_capital.py')
    inputs = [(args.package / name).read_bytes() for name in names]
    outputs = compose_sources(*(data.decode('utf-8') for data in inputs))
    # Every parse, source and helper check precedes creating any output.
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {'scope': 'projection-copy-only', 'release_authorized': False, 'files': {}}
    for name, before, text in zip(names, inputs, outputs):
        data = text.encode('utf-8')
        (args.output / name).write_bytes(data)
        receipt['files'][name] = {'before': blob(before), 'after': blob(data),
                                  'sha256': hashlib.sha256(data).hexdigest()}
    (args.output / 'projection_clone.py').write_bytes(helper)
    receipt['files']['projection_clone.py'] = {'after': blob(helper),
                                               'sha256': HELPER_SHA256}
    (args.output / 'PROJECTION-CLONE.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
