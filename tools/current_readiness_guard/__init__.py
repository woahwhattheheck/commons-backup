from __future__ import annotations

from . import guard as _guard
from ._guard_overrides_v3 import analyze_source, read_source

# Keep the existing public module/API while installing the successor closure layer.
# scan_paths resolves these globals at call time, so CLI/library callers share the
# exact same analyzer and generation-safe source reader.
_guard.analyze_source = analyze_source
_guard._read_source = read_source

__all__ = ["analyze_source"]
