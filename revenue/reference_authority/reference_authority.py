#!/usr/bin/env python3
"""Evidence-bound customer-reference authority with host-owned currentness."""
from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "commons-reference-authority/v2"
TRUST_SCHEMA_VERSION = "commons-reference-authority-trust/v2"
RESULT_SCHEMA_VERSION = "commons-reference-authority-result/v3"
RECEIPT_SCHEMA_VERSION = "commons-reference-authority-receipt/v3"
KEY_ID = "commons-reference-authority-host-v1"
HOST_KEY_ENV = "COMMONS_REFERENCE_AUTHORITY_HMAC_KEY_HEX"
HOST_CURRENT_REGISTRY_PATH = Path("/var/lib/commons/reference-authority/current-authority-registry.json")
MAX_INPUT_BYTES = 2_000_000

ENGAGEMENT_KINDS = {
    "CLIENT_ENGAGEMENT",
    "INTERNAL_ENGINEERING",
    "OPEN_SOURCE_CONTRIBUTION",
    "EXTERNAL_REVIEW_PROGRAM",
    "PROCUREMENT_PURSUIT",
}
DISCLOSURE_USE_CLASSES = {"INTERNAL_ONLY", "CAPABILITY_NARRATIVE", "PROPOSAL_CAPABILITY"}
AUTHORITY_STATUSES = {"AUTHORIZED", "REVOKED"}
CLASSIFICATION_STATUSES = {"CLASSIFIED", "REVOKED"}
COMPARABILITY_STATUSES = {"COMPARABLE", "NOT_COMPARABLE"}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_HEX = re.compile(r"^[0-9a-f]+$")
_EMAIL = re.compile(r"(?i)(?<![\w.%+-])[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.%+-])")
_PHONE = re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]\d{4}(?!\w)")
_SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~-]{8,}|(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|private[_-]?key)\s*[:=])"
)
_PATH = re.compile(r"(?:^|\s)(?:[A-Za-z]:[\\/]|/home/|/Users/|/mnt/|\\\\|\.\.[\\/])")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ReferenceAuthorityError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def record_digest(value: dict[str, Any]) -> str:
    return sha256_hex(canonical_bytes(value))


def _reject_constant(value: str) -> Any:
    raise ReferenceAuthorityError(f"non-finite JSON number forbidden: {value}")


def _nodup(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ReferenceAuthorityError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: bytes | str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_nodup, parse_constant=_reject_constant)
    except ReferenceAuthorityError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReferenceAuthorityError(f"invalid JSON: {exc}") from exc


def _obj(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReferenceAuthorityError(f"{where} must be an object")
    return value


def _arr(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReferenceAuthorityError(f"{where} must be an array")
    return value


def _keys(obj: dict[str, Any], names: set[str], where: str) -> None:
    got = set(obj)
    missing = names - got
    extra = got - names
    if missing:
        raise ReferenceAuthorityError(f"{where} missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ReferenceAuthorityError(f"{where} unknown fields: {', '.join(sorted(extra))}")


def _text(value: Any, where: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ReferenceAuthorityError(f"{where} length/type invalid")
    if value != value.strip():
        raise ReferenceAuthorityError(f"{where} must not have surrounding whitespace")
    if _CONTROL.search(value):
        raise ReferenceAuthorityError(f"{where} contains control characters")
    if _EMAIL.search(value):
        raise ReferenceAuthorityError(f"{where} contains email/contact PII")
    if _PHONE.search(value):
        raise ReferenceAuthorityError(f"{where} contains phone/contact PII")
    if _SECRET.search(value):
        raise ReferenceAuthorityError(f"{where} contains credential-shaped text")
    if _PATH.search(value):
        raise ReferenceAuthorityError(f"{where} contains path-shaped text")
    return value


def _id(value: Any, where: str) -> str:
    value = _text(value, where, 128)
    if not _ID.fullmatch(value):
        raise ReferenceAuthorityError(f"{where} has invalid id syntax")
    return value


def _sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ReferenceAuthorityError(f"{where} must be lowercase SHA-256 hex")
    return value


def _ref(value: Any, where: str, *, opaque: bool = False) -> str:
    value = _text(value, where, 512)
    if opaque and value.startswith("opaque:"):
        if not _ID.fullmatch(value[7:]):
            raise ReferenceAuthorityError(f"{where} has invalid opaque authority handle")
        return value
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise ReferenceAuthorityError(f"{where} must be a public https URL without embedded credentials")
    if _SECRET.search(parts.query) or _SECRET.search(parts.fragment):
        raise ReferenceAuthorityError(f"{where} has secret-shaped query/fragment")
    return value


def _ts(value: Any, where: str) -> str:
    value = _text(value, where, 20)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReferenceAuthorityError(f"{where} must be UTC YYYY-MM-DDTHH:MM:SSZ") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ReferenceAuthorityError(f"{where} is not canonical UTC")
    return value


def _optional_ts(value: Any, where: str) -> str | None:
    return None if value is None else _ts(value, where)


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _int(value: Any, where: str, lo: int = 0, hi: int = 1000) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReferenceAuthorityError(f"{where} must be an integer (bool forbidden)")
    if not lo <= value <= hi:
        raise ReferenceAuthorityError(f"{where} outside [{lo}, {hi}]")
    return value


def _generation_sequence(value: Any, where: str) -> int:
    return _int(value, where, 1, 9_223_372_036_854_775_807)


def _texts(value: Any, where: str) -> list[str]:
    rows = [_text(item, f"{where}[{index}]", 300) for index, item in enumerate(_arr(value, where))]
    if len(rows) > 32:
        raise ReferenceAuthorityError(f"{where} has too many items")
    if len(rows) != len(set(rows)):
        raise ReferenceAuthorityError(f"{where} contains duplicates")
    return sorted(rows)


def _unique(rows: list[dict[str, Any]], key: str, where: str) -> None:
    values = [row[key] for row in rows]
    if len(values) != len(set(values)):
        raise ReferenceAuthorityError(f"duplicate {where} id")


def _evidence(value: Any, index: int = 0) -> dict[str, Any]:
    where = f"evidence[{index}]"
    row = _obj(value, where)
    _keys(
        row,
        {
            "evidence_id",
            "subject",
            "performer",
            "source_ref",
            "source_sha256",
            "observed_result",
            "limitations",
            "disclosure_summary",
        },
        where,
    )
    return {
        "evidence_id": _id(row["evidence_id"], f"{where}.evidence_id"),
        "subject": _text(row["subject"], f"{where}.subject", 160),
        "performer": _text(row["performer"], f"{where}.performer", 160),
        "source_ref": _ref(row["source_ref"], f"{where}.source_ref"),
        "source_sha256": _sha(row["source_sha256"], f"{where}.source_sha256"),
        "observed_result": _text(row["observed_result"], f"{where}.observed_result"),
        "limitations": _texts(row["limitations"], f"{where}.limitations"),
        "disclosure_summary": _text(row["disclosure_summary"], f"{where}.disclosure_summary"),
    }


def evidence_digest(record: dict[str, Any]) -> str:
    return record_digest(_evidence(record))


def _opportunity(value: Any) -> dict[str, Any]:
    row = _obj(value, "opportunity")
    _keys(row, {"opportunity_id", "title"}, "opportunity")
    return {
        "opportunity_id": _id(row["opportunity_id"], "opportunity.opportunity_id"),
        "title": _text(row["title"], "opportunity.title", 240),
    }


def opportunity_digest(record: dict[str, Any]) -> str:
    return record_digest(_opportunity(record))


def _requirement(value: Any, index: int = 0, opportunity_id: str | None = None) -> dict[str, Any]:
    where = f"requirements[{index}]"
    row = _obj(value, where)
    _keys(row, {"requirement_id", "opportunity_id", "label", "required_count"}, where)
    oid = _id(row["opportunity_id"], f"{where}.opportunity_id")
    if opportunity_id is not None and oid != opportunity_id:
        raise ReferenceAuthorityError(f"{where}.opportunity_id does not match packet opportunity")
    return {
        "requirement_id": _id(row["requirement_id"], f"{where}.requirement_id"),
        "opportunity_id": oid,
        "label": _text(row["label"], f"{where}.label", 200),
        "required_count": _int(row["required_count"], f"{where}.required_count", 1, 100),
    }


def requirement_digest(record: dict[str, Any]) -> str:
    return record_digest(_requirement(record))


def normalize_packet(packet: Any) -> dict[str, Any]:
    row = _obj(packet, "packet")
    _keys(row, {"schema_version", "opportunity", "requirements", "evidence"}, "packet")
    if row["schema_version"] != SCHEMA_VERSION:
        raise ReferenceAuthorityError(f"unsupported schema_version: {row['schema_version']!r}")
    opportunity = _opportunity(row["opportunity"])
    oid = opportunity["opportunity_id"]
    requirements = [
        _requirement(value, index, oid)
        for index, value in enumerate(_arr(row["requirements"], "requirements"))
    ]
    evidence = [_evidence(value, index) for index, value in enumerate(_arr(row["evidence"], "evidence"))]
    if not requirements or not evidence:
        raise ReferenceAuthorityError("requirements and evidence must not be empty")
    _unique(requirements, "requirement_id", "requirement")
    _unique(evidence, "evidence_id", "evidence")
    return {
        "schema_version": SCHEMA_VERSION,
        "opportunity": opportunity,
        "requirements": sorted(requirements, key=lambda item: item["requirement_id"]),
        "evidence": sorted(evidence, key=lambda item: item["evidence_id"]),
    }


def _classification(value: Any, index: int) -> dict[str, Any]:
    where = f"authority_registry.classifications[{index}]"
    row = _obj(value, where)
    _keys(
        row,
        {
            "classification_id",
            "evidence_id",
            "evidence_digest",
            "engagement_id",
            "engagement_kind",
            "status",
            "observed_at",
            "expires_at",
            "authority_ref",
            "authority_sha256",
        },
        where,
    )
    kind = _text(row["engagement_kind"], f"{where}.engagement_kind", 40)
    status_value = _text(row["status"], f"{where}.status", 16)
    if kind not in ENGAGEMENT_KINDS:
        raise ReferenceAuthorityError(f"{where}.engagement_kind unsupported")
    if status_value not in CLASSIFICATION_STATUSES:
        raise ReferenceAuthorityError(f"{where}.status unsupported")
    return {
        "classification_id": _id(row["classification_id"], f"{where}.classification_id"),
        "evidence_id": _id(row["evidence_id"], f"{where}.evidence_id"),
        "evidence_digest": _sha(row["evidence_digest"], f"{where}.evidence_digest"),
        "engagement_id": _id(row["engagement_id"], f"{where}.engagement_id"),
        "engagement_kind": kind,
        "status": status_value,
        "observed_at": _ts(row["observed_at"], f"{where}.observed_at"),
        "expires_at": _optional_ts(row["expires_at"], f"{where}.expires_at"),
        "authority_ref": _ref(row["authority_ref"], f"{where}.authority_ref", opaque=True),
        "authority_sha256": _sha(row["authority_sha256"], f"{where}.authority_sha256"),
    }


def _authority(value: Any, index: int, kind: str, requirement_ids: set[str]) -> dict[str, Any]:
    plural = {"d": "disclosures", "p": "permissions", "c": "comparabilities"}[kind]
    where = f"authority_registry.{plural}[{index}]"
    row = _obj(value, where)
    common = {"evidence_id", "evidence_digest", "opportunity_id", "opportunity_digest", "expires_at"}
    if kind == "d":
        names = common | {"authority_id", "use_class", "status", "observed_at", "authority_ref", "authority_sha256"}
    elif kind == "p":
        names = common | {
            "permission_id",
            "requirement_id",
            "requirement_digest",
            "status",
            "observed_at",
            "permission_ref",
            "permission_sha256",
        }
    else:
        names = common | {
            "assessment_id",
            "requirement_id",
            "requirement_digest",
            "status",
            "assessed_at",
            "assessment_ref",
            "assessment_sha256",
        }
    _keys(row, names, where)
    out: dict[str, Any] = {
        "evidence_id": _id(row["evidence_id"], f"{where}.evidence_id"),
        "evidence_digest": _sha(row["evidence_digest"], f"{where}.evidence_digest"),
        "opportunity_id": _id(row["opportunity_id"], f"{where}.opportunity_id"),
        "opportunity_digest": _sha(row["opportunity_digest"], f"{where}.opportunity_digest"),
        "expires_at": _optional_ts(row["expires_at"], f"{where}.expires_at"),
    }
    if kind == "d":
        use_class = _text(row["use_class"], f"{where}.use_class", 32)
        status_value = _text(row["status"], f"{where}.status", 16)
        if use_class not in DISCLOSURE_USE_CLASSES or status_value not in AUTHORITY_STATUSES:
            raise ReferenceAuthorityError(f"{where} unsupported use/status")
        out.update(
            authority_id=_id(row["authority_id"], f"{where}.authority_id"),
            use_class=use_class,
            status=status_value,
            observed_at=_ts(row["observed_at"], f"{where}.observed_at"),
            authority_ref=_ref(row["authority_ref"], f"{where}.authority_ref", opaque=True),
            authority_sha256=_sha(row["authority_sha256"], f"{where}.authority_sha256"),
        )
        return out

    requirement_id = _id(row["requirement_id"], f"{where}.requirement_id")
    if requirement_id not in requirement_ids:
        raise ReferenceAuthorityError(f"{where}.requirement_id unknown to authority registry generation")
    out["requirement_id"] = requirement_id
    out["requirement_digest"] = _sha(row["requirement_digest"], f"{where}.requirement_digest")
    if kind == "p":
        status_value = _text(row["status"], f"{where}.status", 16)
        if status_value not in AUTHORITY_STATUSES:
            raise ReferenceAuthorityError(f"{where}.status unsupported")
        out.update(
            permission_id=_id(row["permission_id"], f"{where}.permission_id"),
            status=status_value,
            observed_at=_ts(row["observed_at"], f"{where}.observed_at"),
            permission_ref=_ref(row["permission_ref"], f"{where}.permission_ref", opaque=True),
            permission_sha256=_sha(row["permission_sha256"], f"{where}.permission_sha256"),
        )
    else:
        status_value = _text(row["status"], f"{where}.status", 24)
        if status_value not in COMPARABILITY_STATUSES:
            raise ReferenceAuthorityError(f"{where}.status unsupported")
        out.update(
            assessment_id=_id(row["assessment_id"], f"{where}.assessment_id"),
            status=status_value,
            assessed_at=_ts(row["assessed_at"], f"{where}.assessed_at"),
            assessment_ref=_ref(row["assessment_ref"], f"{where}.assessment_ref", opaque=True),
            assessment_sha256=_sha(row["assessment_sha256"], f"{where}.assessment_sha256"),
        )
    return out


def _normalize_registry_body(registry: Any) -> dict[str, Any]:
    row = _obj(registry, "authority_registry")
    _keys(
        row,
        {
            "schema_version",
            "key_id",
            "generation_id",
            "generation_sequence",
            "issued_at",
            "requirement_ids",
            "classifications",
            "disclosures",
            "permissions",
            "comparabilities",
        },
        "authority_registry",
    )
    if row["schema_version"] != TRUST_SCHEMA_VERSION:
        raise ReferenceAuthorityError("unsupported authority registry schema")
    if row["key_id"] != KEY_ID:
        raise ReferenceAuthorityError("authority registry key_id mismatch")
    requirement_ids = [
        _id(value, f"authority_registry.requirement_ids[{index}]")
        for index, value in enumerate(_arr(row["requirement_ids"], "authority_registry.requirement_ids"))
    ]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ReferenceAuthorityError("duplicate authority registry requirement id")
    requirement_set = set(requirement_ids)
    classifications = [
        _classification(value, index)
        for index, value in enumerate(_arr(row["classifications"], "authority_registry.classifications"))
    ]
    disclosures = [
        _authority(value, index, "d", requirement_set)
        for index, value in enumerate(_arr(row["disclosures"], "authority_registry.disclosures"))
    ]
    permissions = [
        _authority(value, index, "p", requirement_set)
        for index, value in enumerate(_arr(row["permissions"], "authority_registry.permissions"))
    ]
    comparabilities = [
        _authority(value, index, "c", requirement_set)
        for index, value in enumerate(_arr(row["comparabilities"], "authority_registry.comparabilities"))
    ]
    _unique(classifications, "classification_id", "classification")
    _unique(disclosures, "authority_id", "disclosure authority")
    _unique(permissions, "permission_id", "permission")
    _unique(comparabilities, "assessment_id", "comparability")

    engagement_kind_by_id: dict[str, str] = {}
    for classification in classifications:
        prior = engagement_kind_by_id.setdefault(classification["engagement_id"], classification["engagement_kind"])
        if prior != classification["engagement_kind"]:
            raise ReferenceAuthorityError("engagement_id maps to conflicting engagement kinds")

    return {
        "schema_version": TRUST_SCHEMA_VERSION,
        "key_id": KEY_ID,
        "generation_id": _id(row["generation_id"], "authority_registry.generation_id"),
        "generation_sequence": _generation_sequence(
            row["generation_sequence"], "authority_registry.generation_sequence"
        ),
        "issued_at": _ts(row["issued_at"], "authority_registry.issued_at"),
        "requirement_ids": sorted(requirement_ids),
        "classifications": sorted(classifications, key=lambda item: item["classification_id"]),
        "disclosures": sorted(disclosures, key=lambda item: item["authority_id"]),
        "permissions": sorted(permissions, key=lambda item: item["permission_id"]),
        "comparabilities": sorted(comparabilities, key=lambda item: item["assessment_id"]),
    }


def _host_key() -> bytes:
    raw = os.environ.get(HOST_KEY_ENV)
    if not isinstance(raw, str) or len(raw) < 64 or len(raw) % 2 or not _HEX.fullmatch(raw):
        raise ReferenceAuthorityError(f"trusted host key unavailable/invalid in {HOST_KEY_ENV}")
    key = bytes.fromhex(raw)
    if len(key) < 32:
        raise ReferenceAuthorityError("trusted host key must be at least 256 bits")
    return key


def _registry_mac(body: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, canonical_bytes(body), hashlib.sha256).hexdigest()


def _sign_registry_for_tests(body: dict[str, Any], key_hex: str) -> dict[str, Any]:
    key = bytes.fromhex(key_hex)
    normalized = _normalize_registry_body(body)
    return {
        **normalized,
        "mac": {"algorithm": "HMAC-SHA256", "key_id": KEY_ID, "sha256": _registry_mac(normalized, key)},
    }


def normalize_authority_registry(registry: Any) -> dict[str, Any]:
    row = _obj(registry, "authority_registry_file")
    _keys(
        row,
        {
            "schema_version",
            "key_id",
            "generation_id",
            "generation_sequence",
            "issued_at",
            "requirement_ids",
            "classifications",
            "disclosures",
            "permissions",
            "comparabilities",
            "mac",
        },
        "authority_registry_file",
    )
    body = _normalize_registry_body({key: value for key, value in row.items() if key != "mac"})
    mac = _obj(row["mac"], "authority_registry.mac")
    _keys(mac, {"algorithm", "key_id", "sha256"}, "authority_registry.mac")
    if mac["algorithm"] != "HMAC-SHA256" or mac["key_id"] != KEY_ID:
        raise ReferenceAuthorityError("authority registry MAC algorithm/key mismatch")
    supplied = _sha(mac["sha256"], "authority_registry.mac.sha256")
    expected = _registry_mac(body, _host_key())
    if not hmac.compare_digest(supplied, expected):
        raise ReferenceAuthorityError("authority registry MAC verification failed")
    return {
        **body,
        "mac": {"algorithm": "HMAC-SHA256", "key_id": KEY_ID, "sha256": supplied},
    }


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _resolve(
    rows: list[dict[str, Any]],
    evidence_sha: str,
    now: datetime,
    time_field: str,
    status_field: str,
    good_status: str,
    id_field: str,
    prefix: str,
    opportunity_sha: str | None = None,
    requirement_sha: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not rows:
        return None, f"MISSING_{prefix}"
    if any(_dt(row[time_field]) > now for row in rows):
        return None, f"FUTURE_{prefix}"
    ordered = sorted(rows, key=lambda row: (_dt(row[time_field]), row[id_field]))
    latest_at = _dt(ordered[-1][time_field])
    tied = [row for row in ordered if _dt(row[time_field]) == latest_at]
    if len(tied) > 1 and len({canonical_bytes(row) for row in tied}) > 1:
        return None, f"AMBIGUOUS_{prefix}"
    row = ordered[-1]
    if row["evidence_digest"] != evidence_sha:
        return None, f"{prefix}_EVIDENCE_DIGEST_MISMATCH"
    if opportunity_sha is not None and row["opportunity_digest"] != opportunity_sha:
        return None, f"{prefix}_OPPORTUNITY_DIGEST_MISMATCH"
    if requirement_sha is not None and row["requirement_digest"] != requirement_sha:
        return None, f"{prefix}_REQUIREMENT_DIGEST_MISMATCH"
    if row[status_field] != good_status:
        return None, f"{prefix}_{row[status_field]}"
    if row["expires_at"] is not None and _dt(row["expires_at"]) <= now:
        return None, f"EXPIRED_{prefix}"
    return row, None


def _compile_registry_at(packet: Any, authority_registry: Any, now: datetime) -> dict[str, Any]:
    normalized_packet = normalize_packet(packet)
    authority = normalize_authority_registry(authority_registry)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ReferenceAuthorityError("internal evaluation time must be timezone-aware")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    if _dt(authority["issued_at"]) > now:
        raise ReferenceAuthorityError("authority registry generation is from the future")

    opportunity = normalized_packet["opportunity"]["opportunity_id"]
    opportunity_sha = record_digest(normalized_packet["opportunity"])
    requirement_shas = {
        row["requirement_id"]: record_digest(row) for row in normalized_packet["requirements"]
    }
    evidence = {row["evidence_id"]: row for row in normalized_packet["evidence"]}
    evidence_shas = {key: record_digest(value) for key, value in evidence.items()}
    if set(requirement_shas) - set(authority["requirement_ids"]):
        raise ReferenceAuthorityError("authority registry generation does not admit every packet requirement id")

    classifications = {key: [] for key in evidence}
    disclosures = {key: [] for key in evidence}
    permissions: dict[tuple[str, str], list[dict[str, Any]]] = {}
    comparabilities: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in authority["classifications"]:
        if row["evidence_id"] in classifications:
            classifications[row["evidence_id"]].append(row)
    for row in authority["disclosures"]:
        if row["evidence_id"] in disclosures and row["opportunity_id"] == opportunity:
            disclosures[row["evidence_id"]].append(row)
    for row in authority["permissions"]:
        if row["evidence_id"] in evidence and row["opportunity_id"] == opportunity:
            permissions.setdefault((row["evidence_id"], row["requirement_id"]), []).append(row)
    for row in authority["comparabilities"]:
        if row["evidence_id"] in evidence and row["opportunity_id"] == opportunity:
            comparabilities.setdefault((row["evidence_id"], row["requirement_id"]), []).append(row)

    classification_state: dict[str, tuple[dict[str, Any] | None, str | None]] = {}
    disclosure_state: dict[str, tuple[dict[str, Any] | None, str | None]] = {}
    capability_examples: list[dict[str, Any]] = []
    for evidence_id, evidence_row in sorted(evidence.items()):
        classification, classification_reason = _resolve(
            classifications[evidence_id],
            evidence_shas[evidence_id],
            now,
            "observed_at",
            "status",
            "CLASSIFIED",
            "classification_id",
            "ENGAGEMENT_CLASSIFICATION",
        )
        disclosure, disclosure_reason = _resolve(
            disclosures[evidence_id],
            evidence_shas[evidence_id],
            now,
            "observed_at",
            "status",
            "AUTHORIZED",
            "authority_id",
            "DISCLOSURE_AUTHORITY",
            opportunity_sha,
        )
        classification_state[evidence_id] = (classification, classification_reason)
        disclosure_state[evidence_id] = (disclosure, disclosure_reason)
        if classification and disclosure and disclosure["use_class"] in {
            "CAPABILITY_NARRATIVE",
            "PROPOSAL_CAPABILITY",
        }:
            capability_examples.append(
                {
                    "evidence_id": evidence_id,
                    "engagement_id": classification["engagement_id"],
                    "engagement_kind": classification["engagement_kind"],
                    "subject": evidence_row["subject"],
                    "observed_result": evidence_row["observed_result"],
                    "limitations": evidence_row["limitations"],
                    "disclosure_summary": evidence_row["disclosure_summary"],
                    "use_class": disclosure["use_class"],
                    "classification_id": classification["classification_id"],
                    "disclosure_authority_id": disclosure["authority_id"],
                }
            )

    reference_states: list[dict[str, Any]] = []
    requirement_results: list[dict[str, Any]] = []
    for requirement in normalized_packet["requirements"]:
        requirement_id = requirement["requirement_id"]
        ready_by_engagement: dict[str, list[str]] = {}
        for evidence_id in sorted(evidence):
            reasons: list[str] = []
            classification, classification_reason = classification_state[evidence_id]
            disclosure, disclosure_reason = disclosure_state[evidence_id]
            if not classification:
                reasons.append(classification_reason or "MISSING_ENGAGEMENT_CLASSIFICATION")
            elif classification["engagement_kind"] != "CLIENT_ENGAGEMENT":
                reasons.append("NOT_CLIENT_ENGAGEMENT")
            if not disclosure:
                reasons.append(disclosure_reason or "MISSING_DISCLOSURE_AUTHORITY")
            elif disclosure["use_class"] != "PROPOSAL_CAPABILITY":
                reasons.append("DISCLOSURE_NOT_PROPOSAL_CAPABILITY")
            permission, permission_reason = _resolve(
                permissions.get((evidence_id, requirement_id), []),
                evidence_shas[evidence_id],
                now,
                "observed_at",
                "status",
                "AUTHORIZED",
                "permission_id",
                "REFERENCE_PERMISSION",
                opportunity_sha,
                requirement_shas[requirement_id],
            )
            comparability, comparability_reason = _resolve(
                comparabilities.get((evidence_id, requirement_id), []),
                evidence_shas[evidence_id],
                now,
                "assessed_at",
                "status",
                "COMPARABLE",
                "assessment_id",
                "COMPARABILITY_AUTHORITY",
                opportunity_sha,
                requirement_shas[requirement_id],
            )
            if not permission:
                reasons.append(permission_reason or "MISSING_REFERENCE_PERMISSION")
            if not comparability:
                reasons.append(comparability_reason or "MISSING_COMPARABILITY_AUTHORITY")
            reasons = sorted(set(reasons))
            engagement_id = classification["engagement_id"] if classification else None
            status_value = "REFERENCE_READY_FOR_OWNER_REVIEW" if not reasons else "HOLD"
            if not reasons and engagement_id is not None:
                ready_by_engagement.setdefault(engagement_id, []).append(evidence_id)
            reference_states.append(
                {
                    "evidence_id": evidence_id,
                    "engagement_id": engagement_id,
                    "requirement_id": requirement_id,
                    "status": status_value,
                    "hold_reasons": reasons,
                    "permission_id": permission["permission_id"] if permission else None,
                    "comparability_assessment_id": comparability["assessment_id"] if comparability else None,
                }
            )
        eligible = [
            {"engagement_id": engagement_id, "evidence_ids": sorted(evidence_ids)}
            for engagement_id, evidence_ids in sorted(ready_by_engagement.items())
        ]
        requirement_results.append(
            {
                "requirement_id": requirement_id,
                "label": requirement["label"],
                "required_count": requirement["required_count"],
                "eligible_references": eligible,
                "eligible_count": len(eligible),
                "status": (
                    "SATISFIED_FOR_OWNER_REVIEW"
                    if len(eligible) >= requirement["required_count"]
                    else "HOLD_INSUFFICIENT_REFERENCES"
                ),
            }
        )

    body: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "opportunity_id": opportunity,
        "evaluated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "packet_sha256": sha256_hex(canonical_bytes(normalized_packet)),
        "authority_registry_sha256": sha256_hex(canonical_bytes(authority)),
        "authority_registry_generation_id": authority["generation_id"],
        "authority_registry_generation_sequence": authority["generation_sequence"],
        "capability_examples": capability_examples,
        "reference_states": sorted(reference_states, key=lambda row: (row["requirement_id"], row["evidence_id"])),
        "requirements": sorted(requirement_results, key=lambda row: row["requirement_id"]),
        "authority": {
            "customer_contact": False,
            "reference_contact": False,
            "reference_disclosure": False,
            "proposal_submission": False,
            "contract_commitment": False,
            "payment_or_accounting": False,
            "revenue_recognition": False,
        },
        "truth_boundary": (
            "REFERENCE_READY_FOR_OWNER_REVIEW is authenticated evidence state only; "
            "it does not authorize disclosure, contact, submission, or representation."
        ),
    }
    body["receipt"] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "sha256": sha256_hex(canonical_bytes(body)),
    }
    return body


def compile_registry(packet: Any, authority_registry: Any) -> dict[str, Any]:
    return _compile_registry_at(packet, authority_registry, _now())


def _result(result: Any) -> dict[str, Any]:
    row = _obj(result, "result")
    _keys(
        row,
        {
            "schema_version",
            "opportunity_id",
            "evaluated_at",
            "packet_sha256",
            "authority_registry_sha256",
            "authority_registry_generation_id",
            "authority_registry_generation_sequence",
            "capability_examples",
            "reference_states",
            "requirements",
            "authority",
            "truth_boundary",
            "receipt",
        },
        "result",
    )
    if row["schema_version"] != RESULT_SCHEMA_VERSION:
        raise ReferenceAuthorityError("unsupported result schema")
    _id(row["opportunity_id"], "result.opportunity_id")
    _ts(row["evaluated_at"], "result.evaluated_at")
    _sha(row["packet_sha256"], "result.packet_sha256")
    _sha(row["authority_registry_sha256"], "result.authority_registry_sha256")
    _id(row["authority_registry_generation_id"], "result.authority_registry_generation_id")
    _generation_sequence(
        row["authority_registry_generation_sequence"], "result.authority_registry_generation_sequence"
    )
    receipt = _obj(row["receipt"], "result.receipt")
    _keys(receipt, {"schema_version", "sha256"}, "result.receipt")
    if receipt["schema_version"] != RECEIPT_SCHEMA_VERSION:
        raise ReferenceAuthorityError("unsupported receipt schema")
    _sha(receipt["sha256"], "result.receipt.sha256")
    authority = _obj(row["authority"], "result.authority")
    expected_authority = {
        "customer_contact",
        "reference_contact",
        "reference_disclosure",
        "proposal_submission",
        "contract_commitment",
        "payment_or_accounting",
        "revenue_recognition",
    }
    _keys(authority, expected_authority, "result.authority")
    if any(value is not False for value in authority.values()):
        raise ReferenceAuthorityError("result authority escalation detected")
    _text(row["truth_boundary"], "result.truth_boundary", 300)
    _arr(row["capability_examples"], "result.capability_examples")
    _arr(row["reference_states"], "result.reference_states")
    _arr(row["requirements"], "result.requirements")
    return row


def render_markdown(result: Any) -> str:
    row = _result(result)
    lines = [
        "# Reference authority review",
        "",
        f"- Opportunity: `{row['opportunity_id']}`",
        f"- Evaluated at: `{row['evaluated_at']}`",
        f"- Packet SHA-256: `{row['packet_sha256']}`",
        f"- Trusted authority generation: `{row['authority_registry_generation_id']}`",
        f"- Trusted authority sequence: `{row['authority_registry_generation_sequence']}`",
        f"- Authority registry SHA-256: `{row['authority_registry_sha256']}`",
        f"- Receipt SHA-256: `{row['receipt']['sha256']}`",
        "",
        "## Capability examples authorized for reuse",
    ]
    if row["capability_examples"]:
        lines.extend(
            f"- `{item['evidence_id']}` / engagement `{item['engagement_id']}` — **{item['engagement_kind']}** — "
            f"{item['disclosure_summary']} ({item['use_class']})"
            for item in row["capability_examples"]
        )
    else:
        lines.append("- None.")
    lines += ["", "## Named-reference requirements"]
    for item in row["requirements"]:
        ids = ", ".join(f"`{ref['engagement_id']}`" for ref in item["eligible_references"]) or "none"
        lines.append(
            f"- `{item['requirement_id']}` — **{item['status']}** — "
            f"{item['eligible_count']}/{item['required_count']} distinct trusted engagements; eligible: {ids}"
        )
    lines += ["", "## Per-evidence reference disposition"]
    for item in row["reference_states"]:
        suffix = f": {', '.join(item['hold_reasons'])}" if item["hold_reasons"] else ""
        lines.append(
            f"- `{item['evidence_id']}` -> `{item['requirement_id']}` — **{item['status']}**{suffix}"
        )
    return "\n".join(lines + ["", "## Authority ceiling", "", row["truth_boundary"], ""])


def verify_historical(packet: Any, historical_authority_registry: Any, result: Any) -> dict[str, Any]:
    normalized_result = _result(copy.deepcopy(result))
    receipt = normalized_result["receipt"]
    body = copy.deepcopy(normalized_result)
    del body["receipt"]
    if sha256_hex(canonical_bytes(body)) != receipt["sha256"]:
        raise ReferenceAuthorityError("receipt SHA-256 mismatch")
    historical = normalize_authority_registry(historical_authority_registry)
    if (
        sha256_hex(canonical_bytes(historical)) != normalized_result["authority_registry_sha256"]
        or historical["generation_id"] != normalized_result["authority_registry_generation_id"]
        or historical["generation_sequence"] != normalized_result["authority_registry_generation_sequence"]
    ):
        raise ReferenceAuthorityError("historical authority registry generation mismatch")
    replay = _compile_registry_at(packet, historical_authority_registry, _dt(normalized_result["evaluated_at"]))
    if canonical_bytes(replay) != canonical_bytes(normalized_result):
        raise ReferenceAuthorityError(
            "result does not replay from packet + trusted authority generation at recorded evaluation time"
        )
    return {
        "status": "VERIFIED_HISTORICAL_INTEGRITY_ONLY",
        "receipt_sha256": receipt["sha256"],
        "evaluated_at": normalized_result["evaluated_at"],
        "authority_registry_generation_id": historical["generation_id"],
        "authority_registry_generation_sequence": historical["generation_sequence"],
    }


def _authority_registry_sha(registry: dict[str, Any]) -> str:
    return sha256_hex(canonical_bytes(registry))


def _assert_current_lineage(
    historical: dict[str, Any], current: dict[str, Any]
) -> None:
    historical_sequence = historical["generation_sequence"]
    current_sequence = current["generation_sequence"]
    historical_sha = _authority_registry_sha(historical)
    current_sha = _authority_registry_sha(current)

    if current_sequence < historical_sequence:
        raise ReferenceAuthorityError("current authority registry generation rollback detected")
    if current_sequence == historical_sequence:
        if current["generation_id"] != historical["generation_id"] or current_sha != historical_sha:
            raise ReferenceAuthorityError("current authority registry same-sequence fork detected")
        return
    if current["generation_id"] == historical["generation_id"]:
        raise ReferenceAuthorityError("current authority registry reused generation_id at a newer sequence")
    if _dt(current["issued_at"]) <= _dt(historical["issued_at"]):
        raise ReferenceAuthorityError("newer current authority registry sequence must have later issued_at")


def _verify_current_at(
    packet: Any,
    historical_authority_registry: Any,
    current_authority_registry: Any,
    result: Any,
    now: datetime,
) -> dict[str, Any]:
    historical_verified = verify_historical(packet, historical_authority_registry, result)
    historical = normalize_authority_registry(historical_authority_registry)
    current = normalize_authority_registry(current_authority_registry)
    _assert_current_lineage(historical, current)
    return {
        "status": "VERIFIED_WITH_FRESH_HOST_TIME_REASSESSMENT",
        "historical": historical_verified,
        "current_registry": {
            "generation_id": current["generation_id"],
            "generation_sequence": current["generation_sequence"],
            "sha256": _authority_registry_sha(current),
        },
        "current": _compile_registry_at(packet, current_authority_registry, now),
    }


def _bounded_fd_read(fd: int, label: str) -> bytes:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise ReferenceAuthorityError(f"{label} must be a regular file")
    if before.st_size > MAX_INPUT_BYTES:
        raise ReferenceAuthorityError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
    pieces: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(131_072, MAX_INPUT_BYTES + 1 - total))
        if not chunk:
            break
        pieces.append(chunk)
        total += len(chunk)
        if total > MAX_INPUT_BYTES:
            raise ReferenceAuthorityError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
    after = os.fstat(fd)
    before_generation = (before.st_dev, before.st_ino, before.st_size, getattr(before, "st_mtime_ns", 0))
    after_generation = (after.st_dev, after.st_ino, after.st_size, getattr(after, "st_mtime_ns", 0))
    if before_generation != after_generation:
        raise ReferenceAuthorityError(f"{label} changed while being read")
    return b"".join(pieces)


def _ordinary_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    return flags


def _read_path(path: Path, label: str) -> Any:
    try:
        fd = os.open(path, _ordinary_open_flags())
    except OSError as exc:
        raise ReferenceAuthorityError(f"cannot open {label}: {exc}") from exc
    try:
        return strict_json_loads(_bounded_fd_read(fd, label))
    finally:
        os.close(fd)


def _read_host_current_registry() -> Any:
    # CURRENT verification deliberately has no caller-supplied registry/path surface.
    # The deployment owner must maintain this fixed file in a host-controlled directory.
    path = HOST_CURRENT_REGISTRY_PATH
    if os.name != "posix" or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ReferenceAuthorityError(
            "host current-registry retained component verification requires POSIX O_DIRECTORY/O_NOFOLLOW"
        )
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
    try:
        current_fd = os.open("/", directory_flags)
    except OSError as exc:
        raise ReferenceAuthorityError(f"cannot open trusted current-registry root: {exc}") from exc
    try:
        for component in path.parts[1:-1]:
            try:
                next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            except OSError as exc:
                raise ReferenceAuthorityError(
                    f"cannot retain trusted current-registry path component {component!r}: {exc}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        try:
            file_fd = os.open(path.name, _ordinary_open_flags(), dir_fd=current_fd)
        except OSError as exc:
            raise ReferenceAuthorityError(f"cannot open trusted current authority registry: {exc}") from exc
        try:
            return strict_json_loads(_bounded_fd_read(file_fd, "trusted current authority registry"))
        finally:
            os.close(file_fd)
    finally:
        os.close(current_fd)


def verify_current(packet: Any, historical_authority_registry: Any, result: Any) -> dict[str, Any]:
    """Reassess using the host-owned current registry; callers cannot supply that registry."""
    current = _read_host_current_registry()
    return _verify_current_at(packet, historical_authority_registry, current, result, _now())


def _read(path: Path) -> Any:
    return _read_path(path, str(path))


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("packet", type=Path)
    compile_parser.add_argument("authority_registry", type=Path)
    compile_parser.add_argument("--json-out", required=True, type=Path)
    compile_parser.add_argument("--markdown-out", required=True, type=Path)

    current_parser = sub.add_parser("verify")
    current_parser.add_argument("packet", type=Path)
    current_parser.add_argument("historical_authority_registry", type=Path)
    current_parser.add_argument("result", type=Path)

    historical_parser = sub.add_parser("verify-historical")
    historical_parser.add_argument("packet", type=Path)
    historical_parser.add_argument("historical_authority_registry", type=Path)
    historical_parser.add_argument("result", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "compile":
            if args.json_out.exists() or args.markdown_out.exists():
                raise ReferenceAuthorityError("output path already exists")
            result = compile_registry(_read(args.packet), _read(args.authority_registry))
            _write(args.json_out, canonical_bytes(result) + b"\n")
            _write(args.markdown_out, render_markdown(result).encode("utf-8"))
            print(json.dumps({"status": "COMPILED", "receipt_sha256": result["receipt"]["sha256"]}, sort_keys=True))
            return 0
        packet = _read(args.packet)
        historical = _read(args.historical_authority_registry)
        result = _read(args.result)
        if args.cmd == "verify-historical":
            output = verify_historical(packet, historical, result)
        else:
            output = verify_current(packet, historical, result)
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        return 0
    except ReferenceAuthorityError as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
