#!/usr/bin/env python3
"""Canonical revenue-recovery API with Unicode-safe sensitive-value screening.

The implementation generation is frozen in a non-importable sibling payload so
this facade can harden the shared DLP boundary without duplicating revenue-state
semantics. All exported compiler/receipt functions keep their original behavior;
recursive sensitive-value checks are routed through the canonicalized guard below.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import unicodedata
from pathlib import Path
from typing import Any


_CORE_PATH = Path(__file__).with_name("_revenue_recovery_core_20260917.inc")
_LOADER = importlib.machinery.SourceFileLoader(
    "_commons_revenue_recovery_core_20260917", str(_CORE_PATH)
)
_SPEC = importlib.util.spec_from_loader(_LOADER.name, _LOADER)
if _SPEC is None:
    raise ImportError("unable to construct revenue-recovery core spec")
_CORE = importlib.util.module_from_spec(_SPEC)
_LOADER.exec_module(_CORE)

# Hold the pre-facade implementation. Its recursive lookups are deliberately
# redirected below to this guard; the saved callable still provides the mature
# bounded JSON/query/assignment/url detector graph.
_ORIGINAL_CONTAINS_SENSITIVE_VALUE = _CORE._contains_sensitive_value


def _has_unicode_format_control(value: str) -> bool:
    """Fail closed on invisible Unicode format controls (General Category Cf)."""
    return any(unicodedata.category(character) == "Cf" for character in value)


def _contains_sensitive_value(text: str, query_depth: int) -> bool:
    """Run every detector over raw and percent-decoded NFKC-canonical text.

    The predecessor scanned free-form secret/contact regexes before NFKC, so
    compatibility characters such as U+FF20 FULLWIDTH COMMERCIAL AT could hide
    a human-readable email. Preserve the raw generation (important for encoded
    URL/query structure), but additionally canonicalize the fully bounded
    percent-decoded value *before* the same detector graph runs. Unicode format
    controls fail closed instead of being allowed to split sensitive tokens.
    """
    raw_source = str(text)
    decoded_source, decoding_overflow = _CORE.decode_percent_layers(raw_source)
    if decoding_overflow:
        return True

    canonical_source = unicodedata.normalize("NFKC", decoded_source)
    if (
        _has_unicode_format_control(raw_source)
        or _has_unicode_format_control(decoded_source)
        or _has_unicode_format_control(canonical_source)
    ):
        return True

    # First preserve all predecessor raw/encoded URL and query semantics. The
    # original implementation recursively resolves `_contains_sensitive_value`
    # from its module globals, which is rebound to this facade immediately below.
    if _ORIGINAL_CONTAINS_SENSITIVE_VALUE(raw_source, query_depth):
        return True

    # Then scan the canonical form through the *entire* detector graph, not only
    # its assignment parser. This closes compatibility-character smuggling for
    # free-form contacts, credentials, accounts, private values, paths encoded in
    # structured values, and nested query/JSON content.
    if canonical_source != raw_source:
        if _ORIGINAL_CONTAINS_SENSITIVE_VALUE(canonical_source, query_depth):
            return True
    return False


def contains_sensitive_value(text: str) -> bool:
    return _contains_sensitive_value(text, 0)


# Route every recursive call made by the frozen implementation through the
# hardened boundary. Existing functions retain their original globals/state
# graph; only the shared sensitive-value predicate is substituted.
_CORE._contains_sensitive_value = _contains_sensitive_value
_CORE.contains_sensitive_value = contains_sensitive_value

# Preserve the historical module API. Canonical DLP names above intentionally
# win over same-named core objects; metadata/import plumbing remains private.
_RESERVED = {
    "__name__", "__loader__", "__package__", "__spec__", "__file__", "__cached__",
    "_contains_sensitive_value", "contains_sensitive_value",
}
for _name, _value in vars(_CORE).items():
    if _name not in _RESERVED:
        globals().setdefault(_name, _value)


if __name__ == "__main__":
    sys.exit(_CORE.main())
