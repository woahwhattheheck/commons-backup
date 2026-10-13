# SPDX-License-Identifier: Apache-2.0
"""Raw file-agent adapter for HAZEL's unchanged optional research controller.

Valid in the official file loader's empty execution globals. The exported
package keeps the original entry's sibling SELL directory layout intact.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_module = None


def agent(observation, configuration=None):
    global _module
    if _module is None:
        raw = (configuration or {}).get('__raw_path__') or globals().get('__file__')
        if not raw:
            raise ValueError('File-agent loader must provide __raw_path__')
        here = Path(raw).resolve().parent
        entry = here / 'entry.py'
        if not entry.is_file():
            entry = here / 'policy' / 'entry.py'
        spec = importlib.util.spec_from_file_location('_capital_bundle_entry', entry)
        if spec is None or spec.loader is None:
            raise ImportError('Cannot load the adjacent capital-bundle entry')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _module = module
    return _module.agent(observation, configuration)
