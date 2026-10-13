# SPDX-License-Identifier: Apache-2.0
"""Source-tree alias for the canonical compact SELL snapshot helper.

The release archive packages the attributed sibling bytes directly.  This file
exists only so isolated repository evaluators that expose the canonical lab root
can resolve ``frozen_selected.py`` without caller-specific PYTHONPATH entries.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SOURCE = (Path(__file__).resolve().parent.parent / 'cloud-quickstep' /
           'seller_snapshot.py').resolve()
_SPEC = spec_from_file_location('_titan_seller_snapshot_source', _SOURCE)
if _SPEC is None or _SPEC.loader is None or not _SOURCE.is_file():
    raise ImportError(f'cannot load canonical SELL snapshot source: {_SOURCE}')
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

seller_public_observation = _MODULE.seller_public_observation
__source_path__ = str(_SOURCE)
__all__ = ['seller_public_observation']
