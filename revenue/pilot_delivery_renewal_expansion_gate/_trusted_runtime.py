"""Reload-stable first-load trust root for current pilot-gate semantics.

The public engine may be re-executed with :func:`importlib.reload` or loaded again
under another module name. A process-global ``builtins`` monkeypatch that is active
during that engine execution must not become trusted semantics. This helper is loaded
once with the package and keeps the first-load builtins table plus the first sealed
current-API generation outside later engine module-global re-execution.

The sealed generation includes the public error class as well as compile/verify.  This
matters because an ordinary reload of ``common`` can create a new class object even
when its source is byte-identical.  Engine reload must not split the exception identity
seen by the sealed API from the one exported to callers / caught by the CLI.

The consequence is deliberate: within one Python process, ordinary engine reload is
not a semantic upgrade mechanism. A process restart is required to adopt a new trusted
current generation. Explicit mutation/reload of this private trust-root module or
surgery on its function defaults/closures is outside the cooperative in-process
boundary, just like direct surgery on the engine's sealed function closures.
"""
from __future__ import annotations

import builtins as _builtins


def _build_copy_function():
    snapshot = dict(vars(_builtins))
    copy_dict = dict

    def trusted_builtins_copy(*, _snapshot=snapshot, _copy=copy_dict):
        """Return a fresh copy of the first-load builtins mapping."""
        return _copy(_snapshot)

    return trusted_builtins_copy


def _build_api_registry():
    sealed_runtime = []

    def get_or_build_current_api(builder, *, _sealed=sealed_runtime):
        """Return the process-first-load compile/verify/error generation."""
        if not _sealed:
            _sealed.extend(builder())
        return _sealed[0], _sealed[1], _sealed[2]

    return get_or_build_current_api


trusted_builtins_copy = _build_copy_function()
get_or_build_current_api = _build_api_registry()
del _build_copy_function
del _build_api_registry
del _builtins
