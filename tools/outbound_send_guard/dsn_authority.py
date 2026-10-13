"""Authoritative consumption boundary for normalized RFC DSN receipts.

`dsn_normalizer.verify_receipt()` is intentionally only an integrity check over
caller-supplied receipt bytes. This module binds a receipt back to independently
supplied raw MIME and binding inputs before its event can be consumed as route
lifecycle evidence.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from . import dsn_normalizer as dsn


def _snapshots(
    receipt: Mapping[str, Any],
    raw_mime: bytes | bytearray,
    binding_raw: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    if not isinstance(receipt, Mapping):
        raise dsn.DsnError("authoritative receipt must be an object")
    if not isinstance(binding_raw, Mapping):
        raise dsn.DsnError("authoritative binding must be an object")
    if not isinstance(raw_mime, (bytes, bytearray)):
        raise dsn.DsnError("authoritative raw_mime must be bytes")
    # Freeze all three trust inputs before any parsing/digest work so the
    # authoritative comparison is one coherent observation.
    return deepcopy(dict(receipt)), bytes(raw_mime), deepcopy(dict(binding_raw))


def authoritative_receipt(
    receipt: Mapping[str, Any],
    raw_mime: bytes | bytearray,
    binding_raw: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a source-recomputed receipt or fail closed.

    `raw_mime` and `binding_raw` are independent trusted capture inputs. They
    must not be reconstructed from fields inside `receipt`.
    """
    claimed, source, binding = _snapshots(receipt, raw_mime, binding_raw)

    # Useful malformed/tamper precheck, but never treated as source authority.
    dsn.verify_receipt(claimed)

    # Authority comes from re-running the fail-closed normalizer over the
    # independently supplied source bytes and binding, then requiring the
    # complete canonical receipt to match exactly.
    recomputed = dsn.normalize(source, binding)
    if dsn.canonical_bytes(claimed) != dsn.canonical_bytes(recomputed):
        raise dsn.DsnError(
            "receipt is internally consistent but does not match authoritative raw MIME + binding"
        )
    return recomputed


def verify_authoritative_receipt(
    receipt: Mapping[str, Any],
    raw_mime: bytes | bytearray,
    binding_raw: Mapping[str, Any],
) -> bool:
    """Fail-closed boolean verifier for downstream route-lifecycle consumers."""
    try:
        authoritative_receipt(receipt, raw_mime, binding_raw)
    except (dsn.DsnError, TypeError, ValueError):
        return False
    return True


def authoritative_event(
    receipt: Mapping[str, Any],
    raw_mime: bytes | bytearray,
    binding_raw: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the only DSN event eligible for route-lifecycle insertion.

    The returned event comes from the fresh source recomputation, not from the
    caller's receipt object, eliminating a post-verification receipt mutation
    seam.
    """
    recomputed = authoritative_receipt(receipt, raw_mime, binding_raw)
    event = recomputed.get("event")
    if not isinstance(event, Mapping):  # defensive; normalize currently guarantees this
        raise dsn.DsnError("authoritative receipt has no event object")
    return deepcopy(dict(event))
