# SPDX-License-Identifier: Apache-2.0
"""Fail-closed source injector for Wave-4 F45.

This module intentionally does *not* mint or publish a candidate archive.  The
V5 superiority gate still owns remint authorization.  Once that gate releases,
`inject()` can be composed with the exact pinned base archive and the ordinary
publication-custody path.
"""
from __future__ import annotations

from copy import deepcopy

RUNTIME = "titan_runtime.py"
GUARD = "f45_productive_harvest_collect.py"

_FEATURE_ANCHOR = b"    overflow_safe_drop: bool = False\n"
_BOOL_ANCHOR = b"        bool_fields = (*bool_fields, 'exec_pace', 'overflow_safe_drop')\n"
_METHOD_ANCHOR = b"    def _finish_production(self, obs, returned, cfg=None):\n"
_RETURN_ANCHOR = b"        return returned\n\n    def _seed_selected(self, obs, cfg, selected):\n"

_METHOD = b'''    def _productive_terminal_guard_selected(self, obs, cfg, returned):\n        \"\"\"F45: restore only replay-proven productive unit work.\"\"\"\n        if not getattr(self.features, 'productive_terminal_guard', False):\n            return returned\n        if self.features.consumer != 'frozen' or self.features.terminal_route:\n            self.diagnostics['productive_terminal_guard'] = {\n                'factor': 'F45', 'changed': False,\n                'reason': 'incompatible_consumer_or_terminal_route',\n            }\n            return returned\n        import f45_productive_harvest_collect as f45\n        import mechanics as mechanics_mod\n        result, report = f45.protect_productive_units(\n            mechanics_mod, obs, cfg, self.selected, returned)\n        self.diagnostics['productive_terminal_guard'] = report\n        return result\n\n'''


def _replace_once(raw, anchor, replacement, label):
    count = raw.count(anchor)
    if count != 1:
        raise ValueError(f"F45 expected exactly one {label} anchor; found {count}")
    return raw.replace(anchor, replacement, 1)


def patch_runtime(runtime_source):
    """Activate F45 on one exact runtime shape; drift fails closed."""
    raw = bytes(runtime_source)
    raw = _replace_once(
        raw,
        _FEATURE_ANCHOR,
        _FEATURE_ANCHOR + b"    productive_terminal_guard: bool = True\n",
        "feature",
    )
    raw = _replace_once(
        raw,
        _BOOL_ANCHOR,
        b"        bool_fields = (*bool_fields, 'exec_pace', 'overflow_safe_drop',\n"
        b"                       'productive_terminal_guard')\n",
        "boolean-validation",
    )
    raw = _replace_once(raw, _METHOD_ANCHOR, _METHOD + _METHOD_ANCHOR, "finish-method")
    raw = _replace_once(
        raw,
        _RETURN_ANCHOR,
        b"        returned = self._productive_terminal_guard_selected(obs, cfg or {}, returned)\n"
        b"        return returned\n\n    def _seed_selected(self, obs, cfg, selected):\n",
        "final-return",
    )
    return raw


def inject(base_files, guard_source):
    """Return candidate members with exactly runtime + F45 helper changed.

    No archive is emitted here.  Publication remains behind the external V5
    superiority/remint gate.
    """
    if not isinstance(base_files, dict):
        raise TypeError("base_files must be a member mapping")
    if RUNTIME not in base_files:
        raise ValueError("F45 requires titan_runtime.py in the candidate base")
    if GUARD in base_files:
        raise ValueError("F45 helper already exists in candidate base")
    files = deepcopy(base_files)
    files[RUNTIME] = patch_runtime(files[RUNTIME])
    files[GUARD] = bytes(guard_source).replace(b"\r\n", b"\n")
    return files
