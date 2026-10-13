#!/usr/bin/env python3
"""Chronology-safe reply-to-revenue entrypoint.

All evidence identity, contact-state, and surface authority lives in
``reply_to_revenue_core.py``. This wrapper captures that runtime once, re-exports
its public surface for compatibility, then drops the private core module handle
so wrapper callers do not gain a second mutable dispatch namespace.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_CORE_PATH = Path(__file__).with_name("reply_to_revenue_core.py")
_SPEC = importlib.util.spec_from_file_location(
    "_commons_reply_to_revenue_core",
    _CORE_PATH,
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reply-to-revenue core from {_CORE_PATH}")

_loaded_core = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_loaded_core)

_cli_entrypoint = _loaded_core.main
for _name, _value in vars(_loaded_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

del _name, _value, _loaded_core, _SPEC


def _run_cli(_entrypoint=_cli_entrypoint) -> int:
    return _entrypoint()


del _cli_entrypoint


if __name__ == "__main__":
    raise SystemExit(_run_cli())
