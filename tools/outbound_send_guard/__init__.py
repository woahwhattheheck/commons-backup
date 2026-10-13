"""Fail-closed embedded surface for outbound email deduplication.

Positive CURRENT authority is available only at the direct isolated CLI process
boundary documented in ``cli.py``. Imported package evaluation is deliberately
non-authorizing.
"""

from .guard import GuardError
from .current import (
    CurrentGuardError,
    compile_current,
    compile_current_bytes,
    compile_historical_at,
    verify_current,
    verify_current_bytes,
)

# Compatibility name: embedded evaluation is deliberately HOLD-only for any
# historically positive decision.
evaluate = compile_current

__all__ = [
    "GuardError",
    "CurrentGuardError",
    "compile_current",
    "compile_current_bytes",
    "compile_historical_at",
    "evaluate",
    "verify_current",
    "verify_current_bytes",
]
