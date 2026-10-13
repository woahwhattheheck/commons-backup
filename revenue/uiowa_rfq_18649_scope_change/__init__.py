"""UIOWA-133 isolated scope-change quotation package."""

from __future__ import annotations

try:
    from .calculator import ScopeError, quote
    from .catalog import BASELINE
except ImportError:
    from calculator import ScopeError, quote
    from catalog import BASELINE

__all__ = ["BASELINE", "ScopeError", "quote"]
