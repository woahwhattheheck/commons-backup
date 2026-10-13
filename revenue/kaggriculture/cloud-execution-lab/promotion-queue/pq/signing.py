# SPDX-License-Identifier: Apache-2.0
"""Optional key-based signing for promotion receipts.

Receipts are tamper-evident by default (``integrity.digest`` covers the
canonical bytes). This module adds an optional HMAC-SHA256 signature so the
promotion gate can consume a receipt as an *attributed* artifact: the
signature binds the sealed digest to a key held by the queue operator.

Key handling is deliberately dumb: the key is raw bytes read from a file
the operator points at (``--signing-key``). Key storage, rotation, and
distribution are operator concerns, not queue concerns. Keys never appear
in receipts, logs, or queue state — only the signature does.
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Mapping

from .pinning import canonical_json

SIGNATURE_ALGORITHM = "hmac-sha256-v1"
MIN_KEY_BYTES = 16


class SigningError(Exception):
    pass


def load_key(path: Path) -> bytes:
    """Read a signing key from a file. Fails closed on missing/short keys."""
    key_path = Path(path)
    if not key_path.is_file():
        raise SigningError(f"signing key file missing: {key_path}")
    key = key_path.read_bytes()
    if len(key) < MIN_KEY_BYTES:
        raise SigningError(
            f"signing key too short: {len(key)} bytes < {MIN_KEY_BYTES}"
        )
    return key


def signature_payload(body: Mapping) -> bytes:
    """Canonical bytes the signature covers: the receipt with any existing
    signature stripped, so signing is deterministic and re-verifiable."""
    scrubbed = dict(body)
    integrity = dict(scrubbed.get("integrity", {}))
    integrity.pop("signature", None)
    scrubbed["integrity"] = integrity
    return canonical_json(scrubbed)


def sign_receipt(body: Mapping, key: bytes) -> str:
    """HMAC-SHA256 hex signature over the canonical receipt bytes."""
    if not key or len(key) < MIN_KEY_BYTES:
        raise SigningError("refusing to sign with a missing or short key")
    return hmac.new(key, signature_payload(body), hashlib.sha256).hexdigest()


def verify_signature(body: Mapping, key: bytes) -> tuple[bool, str]:
    """Returns (ok, reason). Fails closed when no signature is present."""
    stored = (body.get("integrity") or {}).get("signature")
    if not stored:
        return False, "no integrity.signature on receipt"
    if not key or len(key) < MIN_KEY_BYTES:
        return False, "missing or short signing key"
    expected = hmac.new(key, signature_payload(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, stored):
        return False, "signature mismatch: receipt bytes or key changed"
    return True, "ok"
