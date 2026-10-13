"""Supported AP batch CLI/API with import-time implementation-generation binding.

The private core retains the original reviewed arithmetic. Exported functions
share a private dependency namespace rather than this mutable facade namespace.
See VERIFIER_GENERATION.md for the in-process boundary and platform assumptions.
"""
from __future__ import annotations

if __package__:
    from . import _batch_reconcile_core as _implementation
    from ._batch_generation import frozen_functions as _freeze
else:
    import _batch_reconcile_core as _implementation
    from _batch_generation import frozen_functions as _freeze

# Preserve the original module's constants, error class and public convenience
# aliases. Private captured module snapshots are deliberately NOT exported.
for _name, _value in vars(_implementation).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

globals().update(_freeze(_implementation))
del _name, _value, _implementation, _freeze

if __name__ == "__main__":
    raise SystemExit(main())
