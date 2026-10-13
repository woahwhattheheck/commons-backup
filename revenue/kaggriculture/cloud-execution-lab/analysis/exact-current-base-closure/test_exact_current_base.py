#!/usr/bin/env python3
"""Verified in-memory loader for test_exact_current_base.py."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import zlib

_PAYLOAD_FILE = 'test_exact_current_base.py.zlib.b64'
_ENCODED_SHA256 = '25f8b9bb40f47b97dd5375031132e5c2bae2fc4b7dce56a7e321c4c009668f33'
_COMPRESSED_SHA256 = 'f786f3a6ae1f9fca3f4da07c1c7ddc3dc26bb567e64f4257d00393e1876364f2'
_LOGICAL_SHA256 = '780ab1d22965819e84066418eb0b6960e0d8c9d7f756b1d0f30780cb69ad2797'
_LOGICAL_BYTES = 11163


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
