#!/usr/bin/env python3
"""Stable public facade for the generation-bound Creator Desk registry.

The recovered implementation is retained byte-for-byte in
``multisite_registry_impl``. This facade preserves the public import path,
normalizes the final missing-root error contract, and keeps test-time Store
substitution visible to the implementation without weakening descriptor
custody.
"""
from __future__ import annotations

from pathlib import Path

import multisite_registry_impl as _impl
from multisite_registry_impl import *  # noqa: F401,F403

_original_open_root = _impl._open_root


def _open_root(path: str | Path, *, create_final: bool):
    try:
        return _original_open_root(path, create_final=create_final)
    except RegistryError as exc:
        prefix = "workspace root component is not provisioned: "
        message = str(exc)
        if not create_final and message.startswith(prefix):
            missing = message[len(prefix):]
            if Path(path).name == missing:
                raise RegistryError("workspace root is not provisioned") from None
        raise


_impl._open_root = _open_root


def provision(registry_path: str | Path, workspace_root: str | Path):
    # Preserve the public module's substitution seam used by hostile tests.
    _impl.Store = Store
    return _impl.provision(registry_path, workspace_root)
