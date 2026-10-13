"""Verify immutable and current organization-pressure receipts."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any

from .core import (
    READY, InputError, VerificationError, _canonical_bytes, _expect_object,
    _hmac_hex, _parse_time, _sha256, strict_json_loads,
)
from .receipt_parse import _normalize_receipt
from .records import _load_authority, _load_ledger
from .storage import _authority_root, _load_active_key, _load_key_by_id


def _utc_now() -> datetime:
    """Return the process-owned current UTC generation used by production."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def verify_receipt_integrity(receipt_data: bytes) -> dict[str, Any]:
    """Verify immutable receipt history using the fixed retained verifier-key root."""
    root = _authority_root()
    try:
        document = _expect_object(strict_json_loads(receipt_data), "receipt")
        body, receipt_hmac, receipt_sha = _normalize_receipt(document)
    except InputError as exc:
        raise VerificationError("receipt is malformed") from exc
    key = _load_key_by_id(root, body["key_id"])
    expected_hmac = _hmac_hex(key, body)
    if not hmac.compare_digest(receipt_hmac, expected_hmac):
        raise VerificationError("receipt HMAC is invalid")
    signed = {**body, "receipt_hmac": receipt_hmac}
    expected_sha = _sha256(_canonical_bytes(signed))
    if not hmac.compare_digest(receipt_sha, expected_sha):
        raise VerificationError("receipt SHA-256 is invalid")
    return {**signed, "receipt_sha256": receipt_sha}


def verify_receipt_current(receipt_data: bytes) -> dict[str, Any]:
    """Verify integrity and reacquire fixed-root live authority for READY receipts."""
    receipt = verify_receipt_integrity(receipt_data)
    if receipt["decision"] != READY:
        return receipt
    now = _utc_now()
    if _parse_time(receipt["valid_until"], "receipt.valid_until") < now:
        raise VerificationError("READY receipt is expired")
    root = _authority_root()
    active = _load_active_key(root)
    if receipt["key_id"] != active.key_id or receipt["verifier_id"] != active.verifier_id:
        raise VerificationError("READY receipt verifier generation is no longer active")
    authority = _load_authority(root, active, receipt["organization_scope_sha256"], now)
    ledger = _load_ledger(root, active, authority, now)
    if authority.policy_generation != receipt["authority_policy_generation"]:
        raise VerificationError("READY receipt policy generation moved")
    if authority.digest != receipt["authority_sha256"]:
        raise VerificationError("READY receipt authority generation moved")
    if ledger.generation != receipt["ledger_generation"] or ledger.digest != receipt["ledger_sha256"]:
        raise VerificationError("READY receipt ledger generation moved")
    return receipt
