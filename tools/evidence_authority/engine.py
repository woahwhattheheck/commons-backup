"""Process-current authority sealing and historical integrity verification.

Positive PROVIDER/BUYER status is derived only from retained source records.
Caller labels, self-hashes, filenames, and candidate-supplied roots never
mint authenticity. compile_current uses verifier-owned process UTC only.
"""

from __future__ import annotations

from datetime import datetime as _DateTime, timezone as _Timezone
from typing import Any, Mapping

from .codec import (
    IMPLEMENTATION_CONTRACT,
    SCHEMA_FACT,
    SCHEMA_RECEIPT,
    GateError,
    format_ts,
    parse_ts,
    require_bool,
    require_exact_keys,
    require_sha256,
    require_text,
    sha256_bytes,
    sha256_value,
)
from .schema import (
    bind_sources,
    identity_tuple,
    payload_digest,
    validate_candidate,
    validate_manifest,
)

_RECEIPT_KEYS = {
    "schema",
    "implementation_contract",
    "evaluation_mode",
    "evaluated_at_utc",
    "status",
    "currentness",
    "candidate_sha256",
    "retained_root_sha256",
    "manifest_sha256",
    "source_set_sha256",
    "derived_authority",
    "reasons",
    "external_authority",
    "buyer_contact_authorized",
    "provider_session_authorized",
    "spend_authorized",
    "payment_authorized",
    "revenue_recognized",
    "receipt_sha256",
}
_FACT_KEYS = {
    "schema",
    "authority_class",
    "issuer_id",
    "subject_id",
    "claim_kind",
    "claim_scope",
    "generation",
    "source_path",
    "source_sha256",
    "issued_at_utc",
    "payload_sha256",
}
_FALSE_AUTHORITY = (
    "external_authority",
    "buyer_contact_authorized",
    "provider_session_authorized",
    "spend_authorized",
    "payment_authorized",
    "revenue_recognized",
)


def _source_set_digest(manifest: Mapping[str, Any], _hash=sha256_value) -> str:
    return _hash([{"path": row["path"], "sha256": row["sha256"]} for row in manifest["sources"]])


def _classify(now: _DateTime, record: Mapping[str, Any], _parse=parse_ts) -> str:
    valid_from = _parse(record["valid_from_utc"], "record.valid_from_utc")
    valid_until = _parse(record["valid_until_utc"], "record.valid_until_utc")
    if now < valid_from:
        return "NOT_YET_VALID"
    if now > valid_until:
        return "EXPIRED"
    return "CURRENT_POSITIVE"


def _evaluate(
    candidate_obj: Any,
    manifest_obj: Any,
    source_bytes: Mapping[str, bytes],
    pinned_root: str,
    now: _DateTime,
    *,
    _cand=validate_candidate,
    _man=validate_manifest,
    _bind=bind_sources,
    _id=identity_tuple,
    _pay=payload_digest,
    _hash=sha256_value,
    _bytes=sha256_bytes,
    _root=require_sha256,
    _canon=_source_set_digest,
    _class=_classify,
    _fmt=format_ts,
) -> dict[str, Any]:
    pinned = _root(pinned_root, "pinned_retained_root")
    candidate = _cand(candidate_obj)
    manifest = _man(manifest_obj)
    if manifest["generation"] != candidate["generation"]:
        raise GateError("candidate generation is not the retained authority generation")
    records = _bind(manifest, source_bytes)
    matches = [
        rec
        for rec in records
        if _id(rec) == _id(candidate) and _pay(rec) == _pay(candidate)
    ]
    reasons: list[str] = []
    facts: list[dict[str, Any]] = []
    currentness = "HOLD"
    status = "HOLD"
    if len(matches) > 1:
        reasons.append("AMBIGUOUS_RETAINED_RECORDS")
    elif len(matches) == 1:
        rec = matches[0]
        clock = _class(now, rec)
        fact = {
            "schema": SCHEMA_FACT,
            "authority_class": rec["authority_class"],
            "issuer_id": rec["issuer_id"],
            "subject_id": rec["subject_id"],
            "claim_kind": rec["claim_kind"],
            "claim_scope": rec["claim_scope"],
            "generation": rec["generation"],
            "source_path": rec["_path"],
            "source_sha256": rec["_sha256"],
            "issued_at_utc": rec["issued_at_utc"],
            "payload_sha256": _pay(rec),
        }
        if clock == "CURRENT_POSITIVE":
            facts.append(fact)
            currentness = "CURRENT_POSITIVE"
            status = "MATCHED"
            reasons.append("RETAINED_RECORD_MATCH")
        else:
            currentness = clock
            reasons.append(f"RECORD_{clock}")
    else:
        transplants = [
            rec
            for rec in records
            if rec["issuer_id"] != candidate["issuer_id"]
            or rec["subject_id"] != candidate["subject_id"]
            or rec["claim_kind"] != candidate["claim_kind"]
            or rec["claim_scope"] != candidate["claim_scope"]
            or rec["generation"] != candidate["generation"]
        ]
        if transplants and any(
            _pay(rec) == _pay(candidate) for rec in transplants
        ):
            reasons.append("IDENTITY_TRANSPLANT")
        else:
            reasons.append("NO_RETAINED_MATCH")
    reasons = sorted(set(reasons))
    return {
        "schema": SCHEMA_RECEIPT,
        "implementation_contract": IMPLEMENTATION_CONTRACT,
        "evaluation_mode": "CURRENT_PROCESS_UTC",
        "evaluated_at_utc": _fmt(now),
        "status": status,
        "currentness": currentness,
        "candidate_sha256": _hash(candidate),
        "retained_root_sha256": pinned,
        "manifest_sha256": _hash(manifest),
        "source_set_sha256": _canon(manifest),
        "derived_authority": facts,
        "reasons": reasons,
        "external_authority": False,
        "buyer_contact_authorized": False,
        "provider_session_authorized": False,
        "spend_authorized": False,
        "payment_authorized": False,
        "revenue_recognized": False,
    }


def _validate_receipt_shape(
    receipt: Any,
    _exact=require_exact_keys,
    _parse=parse_ts,
    _text=require_text,
    _bool=require_bool,
    _hash=sha256_value,
    _sha=require_sha256,
) -> dict[str, Any]:
    _exact(receipt, _RECEIPT_KEYS, "receipt")
    if receipt["schema"] != SCHEMA_RECEIPT or receipt["implementation_contract"] != IMPLEMENTATION_CONTRACT:
        raise GateError("unsupported receipt contract")
    if receipt["evaluation_mode"] != "CURRENT_PROCESS_UTC":
        raise GateError("unsupported receipt evaluation mode")
    _parse(receipt["evaluated_at_utc"], "receipt.evaluated_at_utc")
    if receipt["status"] not in ("MATCHED", "HOLD"):
        raise GateError("receipt.status is invalid")
    if receipt["currentness"] not in (
        "CURRENT_POSITIVE",
        "HISTORICAL_INTEGRITY",
        "NOT_YET_VALID",
        "EXPIRED",
        "HOLD",
    ):
        raise GateError("receipt.currentness is invalid")
    if receipt["status"] == "MATCHED" and receipt["currentness"] != "CURRENT_POSITIVE":
        raise GateError("receipt MATCHED requires CURRENT_POSITIVE")
    if receipt["currentness"] == "CURRENT_POSITIVE" and receipt["status"] != "MATCHED":
        raise GateError("receipt CURRENT_POSITIVE requires MATCHED")
    for key in ("candidate_sha256", "retained_root_sha256", "manifest_sha256", "source_set_sha256", "receipt_sha256"):
        _sha(receipt[key], f"receipt.{key}")
    facts = receipt["derived_authority"]
    if type(facts) is not list:
        raise GateError("receipt.derived_authority must be an array")
    if len(facts) > 1:
        raise GateError("receipt.derived_authority exceeds one fact")
    for i, fact in enumerate(facts):
        _exact(fact, _FACT_KEYS, f"receipt.derived_authority[{i}]")
        if fact["schema"] != SCHEMA_FACT:
            raise GateError("receipt fact schema is invalid")
        _sha(fact["source_sha256"], f"receipt.derived_authority[{i}].source_sha256")
        _sha(fact["payload_sha256"], f"receipt.derived_authority[{i}].payload_sha256")
        _parse(fact["issued_at_utc"], f"receipt.derived_authority[{i}].issued_at_utc")
    if (receipt["currentness"] == "CURRENT_POSITIVE") != (len(facts) == 1):
        raise GateError("receipt fact/currentness mismatch")
    reasons = receipt["reasons"]
    if type(reasons) is not list:
        raise GateError("receipt.reasons must be an array")
    normalized = [_text(item, f"receipt.reasons[{i}]") for i, item in enumerate(reasons)]
    if normalized != sorted(set(normalized)):
        raise GateError("receipt.reasons must be sorted and duplicate-free")
    for key in _FALSE_AUTHORITY:
        if _bool(receipt[key], f"receipt.{key}"):
            raise GateError("receipt authority ceiling violated")
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_sha256")
    if _hash(unsigned) != claimed:
        raise GateError("receipt_sha256 mismatch")
    return dict(receipt)


def _construct_api(
    _evaluate_fn=_evaluate,
    _clock_cls: type[_DateTime] = _DateTime,
    _utc=_Timezone.utc,
    _validator=_validate_receipt_shape,
    _parse=parse_ts,
    _hash=sha256_value,
    _bytes=sha256_bytes,
    _man=validate_manifest,
    _error=GateError,
    _sha=require_sha256,
):
    def _assert_root(manifest_bytes: bytes, pinned_root: str) -> None:
        pinned = _sha(pinned_root, "pinned_retained_root")
        actual = _bytes(manifest_bytes)
        if actual != pinned:
            raise _error("pinned retained root does not match exact manifest bytes")

    def _seal(
        candidate_obj: Any,
        manifest_obj: Any,
        source_bytes: Mapping[str, bytes],
        pinned_root: str,
        now: _DateTime,
    ) -> dict[str, Any]:
        receipt = _evaluate_fn(candidate_obj, manifest_obj, source_bytes, pinned_root, now)
        receipt["receipt_sha256"] = _hash(receipt)
        return receipt

    def _compile_current(
        candidate_obj: Any,
        manifest_bytes: bytes,
        source_bytes: Mapping[str, bytes],
        pinned_root: str,
        *,
        _loads=None,
    ) -> dict[str, Any]:
        from .codec import loads_strict_json

        parser = _loads or loads_strict_json
        if type(manifest_bytes) is not bytes:
            raise _error("manifest must be exact retained bytes")
        _assert_root(manifest_bytes, pinned_root)
        manifest_obj = parser(manifest_bytes)
        return _seal(
            candidate_obj,
            manifest_obj,
            source_bytes,
            pinned_root,
            _clock_cls.now(_utc).replace(microsecond=0),
        )

    def _verify_receipt(
        candidate_obj: Any,
        manifest_bytes: bytes,
        source_bytes: Mapping[str, bytes],
        pinned_root: str,
        receipt: Any,
        *,
        _loads=None,
    ) -> dict[str, Any]:
        """Historical integrity only. Never remints current-positive authority."""
        from .codec import loads_strict_json

        parser = _loads or loads_strict_json
        if type(manifest_bytes) is not bytes:
            raise _error("manifest must be exact retained bytes")
        _assert_root(manifest_bytes, pinned_root)
        checked = _validator(receipt)
        at = _parse(checked["evaluated_at_utc"], "receipt.evaluated_at_utc")
        manifest_obj = parser(manifest_bytes)
        replayed = _seal(candidate_obj, manifest_obj, source_bytes, pinned_root, at)
        if replayed != checked:
            raise _error("receipt semantic replay mismatch")
        return {
            "integrity_valid": True,
            "currentness": "HISTORICAL_INTEGRITY",
            "current_positive": False,
            "external_authority": False,
            "buyer_contact_authorized": False,
            "provider_session_authorized": False,
            "spend_authorized": False,
            "payment_authorized": False,
            "revenue_recognized": False,
        }

    def _verify_current(
        candidate_obj: Any,
        manifest_bytes: bytes,
        source_bytes: Mapping[str, bytes],
        pinned_root: str,
    ) -> dict[str, Any]:
        fresh = _compile_current(candidate_obj, manifest_bytes, source_bytes, pinned_root)
        return {
            "integrity_valid": True,
            "currentness": fresh["currentness"],
            "current_positive": fresh["currentness"] == "CURRENT_POSITIVE",
            "status": fresh["status"],
            "receipt_sha256": fresh["receipt_sha256"],
            "external_authority": False,
            "buyer_contact_authorized": False,
            "provider_session_authorized": False,
            "spend_authorized": False,
            "payment_authorized": False,
            "revenue_recognized": False,
        }

    return _compile_current, _verify_receipt, _verify_current


compile_current, verify_receipt, verify_current = _construct_api()
del _construct_api
