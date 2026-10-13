# SPDX-License-Identifier: MIT
"""Export the frozen T05 x SELL runtime with the existing cloud-pack builder."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build(destination: Path):
    base = HERE.parent
    freeze = json.loads((HERE / 'SOURCE-FREEZE.json').read_text())
    def source(name):
        aliases = {'cloud-terminal-routing/terminal.py': HERE / 'vendor/terminal.py',
                   'cloud-terminal-routing/main.py': HERE / 'vendor/t05-main.py'}
        return aliases.get(name, base / name)
    for name, pin in freeze['runtime'].items():
        if hashlib.sha256(source(name).read_bytes()).hexdigest() != pin['sha256']:
            raise ValueError(f'Runtime changed after freeze: {name}')
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    files = {'main.py': HERE / 'main.py', 'composition.py': HERE / 'composition.py',
             'vendor/terminal.py': HERE / 'vendor/terminal.py',
             'SOURCE-FREEZE.json': HERE / 'SOURCE-FREEZE.json',
             'NOTICE': HERE / 'NOTICE',
             'LICENSE': HERE / 'LICENSE'}
    vendor = base / 'cloud-titan-composition/vendor/sell'
    for path in sorted(vendor.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            files['vendor/sell/' + str(path.relative_to(vendor))] = path
    spec = {'schema_version': 1, 'label': 'OSPREY T05 x frozen SELL v1',
            'source_callable': 'agent',
            'provenance': {'selection_status': 'Independent local candidate; shared TITAN selection unchanged',
                           'terminal_source': freeze['component_refs']['terminal'],
                           'sell_source': freeze['component_refs']['sell'],
                           'licenses': 'New bridge MIT; unchanged T05, SELL and inherited Arlene Apache-2.0'},
            'files': {name: {'source': str(path.resolve()),
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                      for name, path in files.items()}}
    spec_path = destination / 'spec.json'
    spec_path.write_text(json.dumps(spec, indent=2) + '\n')
    source = importlib.util.spec_from_file_location('osprey_existing_pack', base / 'cloud-pack/pack.py')
    pack = importlib.util.module_from_spec(source)
    source.loader.exec_module(pack)
    receipt = pack.build(spec_path, destination / 'bundle')
    pack.verify(destination / 'bundle', destination / 'extracted')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    print(json.dumps(build(parser.parse_args().destination), indent=2))
