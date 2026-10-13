#!/usr/bin/env python3
"""Transparent loader for the compressed, reviewable studio implementation."""
from pathlib import Path
import gzip
_payload = Path(__file__).with_name("studio_impl.py.gz")
exec(compile(gzip.decompress(_payload.read_bytes()), str(_payload) + "::studio_impl.py", "exec"), globals(), globals())
