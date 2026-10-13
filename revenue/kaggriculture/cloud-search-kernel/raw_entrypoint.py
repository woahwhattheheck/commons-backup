# SPDX-License-Identifier: Apache-2.0
"""File-agent wrapper for the unchanged T06 runtime.

Kaggle's file loader supplies __raw_path__ in configuration, not __file__ in
its exec namespace. Resolve assets on first call, after that path is available.
The existing pack.py exports this wrapper as main.py; no hosted upload occurs.
"""
import importlib.util as _util
from pathlib import Path as _Path
import sys as _sys

_runner = None


def agent(observation, configuration=None):
    global _runner
    if _runner is None:
        config = configuration if configuration is not None else {}
        filename = config.get('__raw_path__') or globals().get('__file__')
        if not filename:
            raise ValueError('T06 needs the file-loader path or a normal module import')
        directory = _Path(filename).resolve().parent
        # The exported layout nests the frozen runtime so its existing relative
        # vendor paths remain valid. A normal source import uses the sibling.
        entry = directory / 'cloud-search-kernel' / 'entrypoint.py'
        if not entry.is_file():
            entry = directory / 'entrypoint.py'
        if not entry.is_file():
            raise FileNotFoundError('T06 entrypoint.py is absent from the bundle')
        _sys.path.insert(0, str(entry.parent))
        spec = _util.spec_from_file_location('_t06_file_bundle_entry', entry)
        if spec is None or spec.loader is None:
            raise ImportError('Cannot create the T06 file-bundle module')
        module = _util.module_from_spec(spec)
        _sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _runner = module.agent
    return _runner(observation, configuration)
