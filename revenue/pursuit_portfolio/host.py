"""Public fixed-host facade for pursuit-portfolio current authority.

Production compile and verification always cross a fresh ``python -I`` process.
The candidate supplies bounded JSON/bytes only; the child derives the effective
account root and real UTC after startup and reacquires every trust capability.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import host_kernel as _kernel
from .fresh_boundary import build_entrypoints


# Re-export deterministic component types/helpers for historical tests and
# inspection.  Production entrypoints below never dereference these facade
# globals after import.
for _name in dir(_kernel):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_kernel, _name)

if os.name == "posix":
    HOST_ROOT = _kernel.fixed_host_root()
else:
    HOST_ROOT = Path("/__pursuit_portfolio_unsupported_host_root__")
HOST_KEY_PATH = HOST_ROOT / "authority-key.json"
HOST_FLOOR_PATH = HOST_ROOT / "authority-floor.json"


def _load_host_key_from(path):
    return _kernel.load_host_key_from(path)


def _load_host_floor_from(path, key, trusted_now):
    return _kernel.load_host_floor_from(path, key, trusted_now)


compile_current, verify_current = build_entrypoints()

__all__ = sorted(
    name for name in globals() if not name.startswith("__") and name != "_kernel"
)
