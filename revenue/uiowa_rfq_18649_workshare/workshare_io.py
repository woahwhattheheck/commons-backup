#!/usr/bin/env python3
"""Compatibility facade for descriptor-safe workshare I/O."""
from workshare_read import _stat_fingerprint, _read_bounded_regular, _load_file
from workshare_write import (
    _directory_fingerprint, _open_parent_chain, _verify_parent_chain, _write_exclusive,
)
