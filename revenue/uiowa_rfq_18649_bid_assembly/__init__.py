"""UIOWA-136 isolated bid-assembly package."""

from __future__ import annotations

try:
    from .assembler import AssemblyError, BidAssembly, load_manifest
    from .canonical import AUTHORITY, PINNED_COMMERCIAL
except ImportError:
    from assembler import AssemblyError, BidAssembly, load_manifest
    from canonical import AUTHORITY, PINNED_COMMERCIAL

__all__ = [
    "AUTHORITY",
    "AssemblyError",
    "BidAssembly",
    "PINNED_COMMERCIAL",
    "load_manifest",
]
