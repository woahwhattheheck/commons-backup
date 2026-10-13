from __future__ import annotations

import hashlib
import hmac
from typing import Any

from ._authority import _authenticate_envelope, _parse_key_document
from ._common import QualificationInputError, _canonical_bytes, _instant, _keys, _object
from .gate import _evaluate


def evaluate_with_authenticated_authority(
    snapshot: Any,
    *,
    evaluated_at: str,
    expected_rfp_sha256: str,
    envelope: Any,
    key_document: Any,
    emulate_host: bool = False,
) -> dict[str, Any]:
    authority = _authenticate_envelope(envelope, key_document)
    return _evaluate(
        snapshot,
        evaluated=_instant(evaluated_at, "evaluated_at"),
        expected_rfp_sha256=expected_rfp_sha256,
        authority=authority,
        semantic_authority_mode="HOST_HMAC" if emulate_host else "TEST_AUTHENTICATED",
        clock_authority="TEST_PROCESS_UTC",
    )


def sign_envelope(unsigned_envelope: Any, key_document: Any) -> dict[str, Any]:
    key_id, key = _parse_key_document(key_document)
    envelope = _object(unsigned_envelope, "unsigned semantic authority envelope")
    _keys(
        envelope,
        {"schema", "key_id", "generation_id", "issued_at", "attestations"},
        "unsigned semantic authority envelope",
    )
    if envelope["key_id"] != key_id:
        raise QualificationInputError("test envelope key mismatch")
    signed = dict(envelope)
    signed["hmac_sha256"] = hmac.new(
        key,
        _canonical_bytes(envelope),
        hashlib.sha256,
    ).hexdigest()
    return signed
