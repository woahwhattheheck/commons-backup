"""Search-index-lag-safe retained custody publication preflight."""

from .core import compile_snapshot, verify_compilation
from .schema import ValidationError

__all__ = ["compile_snapshot", "verify_compilation", "ValidationError"]
