"""Shared command-center record helpers; no provider dispatch or runtimes.

Workstreams and collectors import these helpers without closing over CommandCenter
source catalogs. Core re-exports the same names for existing callers.
"""
from __future__ import annotations

import json
import math
import re


class CoreError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = int(status)
        self.message = str(message)


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise CoreError(400, "Payload must contain finite JSON values.") from None


_SECRET_KEYS = re.compile(
    r"^(?:password|passwd|secret|token|api[_-]?key|authorization|cookie|"
    r"private[_-]?key|recovery[_-]?code|credential[_-]?value|access[_-]?token|"
    r"refresh[_-]?token|client[_-]?secret)$", re.I)
_SECRET_TEXT = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{12,}|\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_-]{8,}"
    r"|\bxox[bpars]-[A-Za-z0-9-]{8,}"
    r"|\bBearer\s+[A-Za-z0-9._~+/-]{8,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:password|api[_-]?key|access[_-]?token|refresh[_-]?token)"
    r"\s*[:=]\s*[^\s,;]+)", re.I)


def _text(value, limit=4000):
    if value is None:
        return ""
    if not isinstance(value, (str, int, float, bool)):
        raise CoreError(400, "Expected a scalar metadata value.")
    return _SECRET_TEXT.sub("[redacted]", str(value))[:limit]


def _no_secret_fields(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_KEYS.fullmatch(str(key)):
                raise CoreError(400, "Credential values belong in the shared secure facility, not metadata.")
            _no_secret_fields(item)
    elif isinstance(value, list):
        for item in value:
            _no_secret_fields(item)


def _metadata(value, depth=0):
    """Bounded JSON metadata with common credential forms redacted."""
    if depth > 8:
        raise CoreError(400, "Metadata is nested too deeply.")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise CoreError(400, "Metadata numbers must be finite.")
        return value
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        if len(value) > 100:
            raise CoreError(400, "Metadata lists are limited to 100 entries.")
        return [_metadata(item, depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 100:
            raise CoreError(400, "Metadata objects are limited to 100 fields.")
        return {_text(key, 120): _metadata(item, depth + 1)
                for key, item in value.items()}
    raise CoreError(400, "Unsupported metadata value.")
