from __future__ import annotations

import hashlib
import hmac
from typing import Any

from ._common import (
    AUTHORITY_ENVELOPE_SCHEMA,
    AUTHORITY_KEY_SCHEMA,
    QualificationInputError,
    _SEMANTIC_DOCUMENTS,
    _HEX_KEY,
    _canonical_bytes,
    _hex64,
    _identifier,
    _instant,
    _keys,
    _object,
    _string,
    _bool,
    digest,
    GOOD_STANDING_DOCUMENT,
)

def _parse_key_document(value: Any) -> tuple[str, bytes]:
    obj = _object(value, "authority key")
    _keys(obj, {"schema", "key_id", "key_hex"}, "authority key")
    if obj["schema"] != AUTHORITY_KEY_SCHEMA:
        raise QualificationInputError("authority key schema mismatch")
    key_id = _identifier(obj["key_id"], "authority key key_id")
    key_hex = _string(obj["key_hex"], "authority key key_hex", max_bytes=256)
    if _HEX_KEY.fullmatch(key_hex) is None or len(key_hex) % 2:
        raise QualificationInputError("authority key must be 32..128 bytes of lowercase hex")
    key = bytes.fromhex(key_hex)
    if len(key) < 32 or len(key) > 128:
        raise QualificationInputError("authority key length is outside 32..128 bytes")
    return key_id, key


_ATTESTATION_FIELDS = {
    "attestation_id",
    "document_id",
    "document_evidence_sha256",
    "semantic_kind",
    "issuer",
    "issued_at",
    "period_end_at",
    "most_recent",
    "verified_at",
    "source_ref",
    "source_evidence_sha256",
}


def _validate_attestation(raw: Any, index: int) -> dict[str, Any]:
    name = f"semantic authority attestations[{index}]"
    row = _object(raw, name)
    _keys(row, _ATTESTATION_FIELDS, name)
    attestation_id = _identifier(row["attestation_id"], f"{name}.attestation_id")
    document_id = _identifier(row["document_id"], f"{name}.document_id")
    if document_id not in _SEMANTIC_DOCUMENTS:
        raise QualificationInputError(f"{name}.document_id is not a compiled semantic document")
    document_sha = _hex64(row["document_evidence_sha256"], f"{name}.document_evidence_sha256")
    semantic_kind = _identifier(row["semantic_kind"], f"{name}.semantic_kind")
    verified_at = _instant(row["verified_at"], f"{name}.verified_at")
    source_ref = _identifier(row["source_ref"], f"{name}.source_ref")
    source_sha = _hex64(row["source_evidence_sha256"], f"{name}.source_evidence_sha256")
    if document_id == GOOD_STANDING_DOCUMENT:
        issuer = _string(row["issuer"], f"{name}.issuer")
        issued_at = _instant(row["issued_at"], f"{name}.issued_at")
        if row["period_end_at"] is not None or row["most_recent"] is not None:
            raise QualificationInputError("Good Standing attestation has audit-only fields")
        period_end_at = None
        most_recent = None
    else:
        if row["issuer"] is not None or row["issued_at"] is not None:
            raise QualificationInputError("audit attestation has Good-Standing-only fields")
        period_end_at = _instant(row["period_end_at"], f"{name}.period_end_at")
        most_recent = _bool(row["most_recent"], f"{name}.most_recent")
        issuer = None
        issued_at = None
    return {
        "attestation_id": attestation_id,
        "document_id": document_id,
        "document_evidence_sha256": document_sha,
        "semantic_kind": semantic_kind,
        "issuer": issuer,
        "issued_at": issued_at,
        "period_end_at": period_end_at,
        "most_recent": most_recent,
        "verified_at": verified_at,
        "source_ref": source_ref,
        "source_evidence_sha256": source_sha,
    }


def _authenticate_envelope(envelope_value: Any, key_value: Any) -> dict[str, Any]:
    key_id, key = _parse_key_document(key_value)
    envelope = _object(envelope_value, "semantic authority envelope")
    _keys(
        envelope,
        {"schema", "key_id", "generation_id", "issued_at", "attestations", "hmac_sha256"},
        "semantic authority envelope",
    )
    if envelope["schema"] != AUTHORITY_ENVELOPE_SCHEMA:
        raise QualificationInputError("semantic authority envelope schema mismatch")
    if _identifier(envelope["key_id"], "semantic authority envelope key_id") != key_id:
        raise QualificationInputError("semantic authority key_id mismatch")
    generation_id = _identifier(envelope["generation_id"], "semantic authority generation_id")
    issued_at = _instant(envelope["issued_at"], "semantic authority issued_at")
    supplied_mac = _hex64(envelope["hmac_sha256"], "semantic authority hmac_sha256")
    signed = dict(envelope)
    signed.pop("hmac_sha256")
    expected_mac = hmac.new(key, _canonical_bytes(signed), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_mac, expected_mac):
        raise QualificationInputError("semantic authority HMAC mismatch")
    raw_rows = envelope["attestations"]
    if type(raw_rows) is not list or len(raw_rows) > 32:
        raise QualificationInputError("semantic authority attestations must be a bounded array")
    rows = [_validate_attestation(row, idx) for idx, row in enumerate(raw_rows)]
    ids = [row["attestation_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise QualificationInputError("semantic authority contains duplicate attestation_id")
    seams = [(row["document_id"], row["document_evidence_sha256"]) for row in rows]
    if len(seams) != len(set(seams)):
        raise QualificationInputError("semantic authority contains duplicate document/hash seam")
    for row in rows:
        if row["verified_at"] > issued_at:
            raise QualificationInputError("attestation verification cannot postdate envelope issuance")
    return {
        "key_id": key_id,
        "generation_id": generation_id,
        "issued_at": issued_at,
        "rows": rows,
        "envelope_sha256": digest(envelope),
    }
