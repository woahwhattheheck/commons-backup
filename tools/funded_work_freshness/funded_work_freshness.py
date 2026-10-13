#!/usr/bin/env python3
"""Fail-closed freshness preflight for advertised funded work.

Aggregator state is discovery evidence only. A candidate becomes actionable only
when fresh canonical GitHub evidence still shows an open, unoccupied, sufficiently
specified, funded opportunity. The tool performs read-only HTTP GETs and never
claims work, comments, contacts sponsors, or treats an advertised amount as cash.
"""
from __future__ import annotations

from cli import main
from constants import MAX_HTTP_BYTES, SCHEMA
from engine import preflight
from errors import EvidenceError, PreflightInputError
from models import Candidate, Response, Transport
from transport import UrlLibTransport, read_bounded, validate_public_destination

# Compatibility exports retained for existing fixtures and direct imports.
_read_bounded = read_bounded
_validate_public_destination = validate_public_destination

__all__ = [
    "Candidate",
    "EvidenceError",
    "MAX_HTTP_BYTES",
    "PreflightInputError",
    "Response",
    "SCHEMA",
    "Transport",
    "UrlLibTransport",
    "preflight",
]

if __name__ == "__main__":
    raise SystemExit(main())
