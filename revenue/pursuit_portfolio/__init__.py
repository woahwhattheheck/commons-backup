"""Evidence-bound pursuit portfolio allocation.

Top-level package exports are the fixed-host, host-sealed current-use path.
Deterministic engine/replay helpers and explicit-key test machinery remain in
``core`` and ``current``; they are not production authority roots.
"""
from .core import PortfolioError
from .current import load_current_input
from .host import compile_current, verify_current
from .publisher import publish_current, read_current

__all__ = [
    "PortfolioError",
    "compile_current",
    "load_current_input",
    "publish_current",
    "read_current",
    "verify_current",
]
