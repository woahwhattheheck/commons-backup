# SPDX-License-Identifier: Apache-2.0
"""Compose four reviewed native optimizer components; never install production.

The existing peer files are dependencies, not copied implementations. Exact
source/component pins and a fixed order prevent a whole-module donor from
rolling back a previously applied peer. Only selected_sell_core is emitted.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

SOURCE_GIT = 'f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3'
COMPONENTS = (
    ('SIEVE', 'selected-incumbent-bound/patch_selected_incumbent.py',
     '5ade322bfdc916b7d3ac071ab2e3fc60fb1f0db0'),
    ('MEADOW', 'marketpath-receipt-prefix/marketpath_receipt_prefix.py',
     '6b8a32669d75f6a239c3a2b78cafa6c92402d719'),
    ('EVENTPATH', 'score-eventpath/build_score_eventpath.py',
     'f7ae150bc47058393552fd1d7600b7f5d5aaa84c'),
    ('CACHELIFE', 'optimizer-cache-lifetime/repair_cache_lifetime.py',
     'e48861b8fe186ded0337aa66ba68833b760708b3'),
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def load_components(root: Path):
    """Authenticate all dependencies before importing any of them."""
    sources = []
    for name, relative, expected in COMPONENTS:
        path = root / relative
        raw = path.read_bytes()
        if git_blob(raw) != expected:
            raise ValueError(f'{name} component identity mismatch: {path}')
        sources.append((name, path, raw))
    modules = {}
    for name, path, raw in sources:
        spec = importlib.util.spec_from_file_location('_weave_' + name.lower(), path)
        module = importlib.util.module_from_spec(spec)
        # Compile the authenticated bytes, avoiding loader/cache TOCTOU reads.
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        modules[name] = module
    return modules


def compose(source: bytes, component_root: Path):
    """Return (exact assembled source, provenance); accept only reviewed parent."""
    if git_blob(source) != SOURCE_GIT:
        raise ValueError('reviewed selected_sell_core parent required; refusing source drift')
    parts = load_components(Path(component_root))
    stages = []
    value = source
    for name, path, expected in COMPONENTS:
        before = git_blob(value)
        if name == 'SIEVE':
            value = parts[name].transform(value)
        elif name == 'MEADOW':
            value = parts[name].transform(value.decode('utf-8')).encode('utf-8')
        elif name == 'EVENTPATH':
            value = parts[name].compose(value.decode('utf-8')).encode('utf-8')
        else:
            value = parts[name].transform(value.decode('utf-8'), before).encode('utf-8')
        compile(value, 'selected_sell_core.py', 'exec')
        stages.append({'component': name, 'component_path': path,
                       'component_git': expected, 'input_git': before,
                       'output_git': git_blob(value),
                       'output_sha256': hashlib.sha256(value).hexdigest()})
    return value, {'schema': 'titan-v4-native-optimizer-stack/v1',
                   'source_git': SOURCE_GIT, 'stages': stages,
                   'output_git': git_blob(value),
                   'output_sha256': hashlib.sha256(value).hexdigest(),
                   'runtime_installation': False, 'default_change': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--components-root', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('input and staging output must differ')
    try:
        value, receipt = compose(args.source.read_bytes(), args.components_root)
        # Never overwrite an existing file or symlink, even an earlier candidate.
        with args.output.open('xb') as handle:
            handle.write(value)
    except (OSError, ValueError, SyntaxError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
