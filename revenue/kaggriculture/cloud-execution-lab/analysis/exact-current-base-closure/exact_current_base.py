#!/usr/bin/env python3
"""Verified in-memory loader for exact_current_base.py."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import zlib

_PAYLOAD_FILE = 'exact_current_base.py.zlib.b64'
_ENCODED_SHA256 = 'f0afb779f235a2a748227b7045590f3bb727b64ac6cd2f8e3735b4f81d3e5685'
_COMPRESSED_SHA256 = '2f9f9e4eeceda903798c111b42c02247e5860d4d3ff05a68fb879daae1899050'
_LOGICAL_SHA256 = '7caab9b80102299bba02034158f735a6b371568ff4127b246aaccf35ae17c072'
_LOGICAL_BYTES = 24465


def _load() -> bytes:
    encoded = Path(__file__).with_name(_PAYLOAD_FILE).read_bytes()
    if hashlib.sha256(encoded).hexdigest() != _ENCODED_SHA256:
        raise RuntimeError("encoded payload SHA-256 mismatch")
    if not encoded.endswith(b"\n") or b"\n" in encoded[:-1] or b"\r" in encoded:
        raise RuntimeError("encoded payload must be one canonical line")
    compressed = base64.b64decode(encoded[:-1], validate=True)
    if hashlib.sha256(compressed).hexdigest() != _COMPRESSED_SHA256:
        raise RuntimeError("compressed payload SHA-256 mismatch")
    decoder = zlib.decompressobj()
    logical = decoder.decompress(compressed) + decoder.flush()
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise RuntimeError("compressed payload framing mismatch")
    if len(logical) != _LOGICAL_BYTES or hashlib.sha256(logical).hexdigest() != _LOGICAL_SHA256:
        raise RuntimeError("logical payload identity mismatch")
    return logical


_LOGICAL_SOURCE = _load()
_GLOBALS = globals()
_GLOBALS["_GUARD_LOGICAL_SOURCE_BYTES"] = _LOGICAL_SOURCE
exec(compile(_LOGICAL_SOURCE, str(Path(__file__).with_suffix(".logical.py")), "exec"), _GLOBALS, _GLOBALS)
