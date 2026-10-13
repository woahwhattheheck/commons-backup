"""Reload-stable public facade for the NIH SPARK pre-launch baseline.

The byte-exact landed predecessor implementation lives in the private
`_baseline_core` module. Public imports stay on this facade so every ordinary
`importlib.reload(baseline)` generation deterministically re-exports the hardened
retrieval authority instead of reviving the predecessor evaluator/receipt path.
"""

from __future__ import annotations

from . import _baseline_core as _core

_AUTHORITY_NAMES = frozenset({
    "evaluate_bundle",
    "build_run_receipt",
    "verify_run_receipt",
})

# Preserve the complete historical direct-baseline surface, including private
# helpers used by repository tests. Never copy the predecessor authority callables
# into the already-published facade: importlib.reload() executes in-place, so a
# concurrent holder of this module must continue to see the previous hardened
# bindings until the new hardened bindings below are assigned.
#
# Objects defined by the core keep their code and globals but report the historical
# public module for introspection/pickling.
for _name, _value in vars(_core).items():
    if _name in _AUTHORITY_NAMES:
        continue
    if _name.startswith("__") and _name.endswith("__"):
        continue
    if getattr(_value, "__module__", None) == _core.__name__:
        try:
            _value.__module__ = __name__
        except (AttributeError, TypeError):
            pass
    globals()[_name] = _value

# Resolve the three public authority entrypoints only from the hardened module.
# On reload the previous hardened generation stays visible throughout the core-copy
# loop; these assignments then atomically replace each name one-by-one with the
# current hardened generation. retrieval_authority depends only on the private
# core, so this import has no baseline<->authority cycle.
from .retrieval_authority import (  # noqa: E402
    build_run_receipt,
    evaluate_bundle,
    verify_run_receipt,
)

del _AUTHORITY_NAMES
del _core
del _name
del _value
