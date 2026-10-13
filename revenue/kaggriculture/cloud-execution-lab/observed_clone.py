# SPDX-License-Identifier: Apache-2.0
"""Source-tree alias for the canonical observed-clone implementation.

The release archive packages the attributed sibling bytes directly.  This file
exists only so isolated repository evaluators that expose the canonical lab root
can resolve ``scheduler.py`` without caller-specific PYTHONPATH entries.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SOURCE = (Path(__file__).resolve().parent.parent / 'cloud-runtime-pulse' /
           'observed_clone.py').resolve()
_SPEC = spec_from_file_location('_titan_observed_clone_source', _SOURCE)
if _SPEC is None or _SPEC.loader is None or not _SOURCE.is_file():
    raise ImportError(f'cannot load canonical observed-clone source: {_SOURCE}')
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

detached_json_value = _MODULE.detached_json_value
__source_path__ = str(_SOURCE)
__all__ = ['detached_json_value']
