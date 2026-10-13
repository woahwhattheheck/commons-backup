from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA = "commons-data-license/v1"
RECEIPT_SCHEMA = "commons-data-license-receipt/v1"
READY = "READY_FOR_HUMAN_LICENSE_REVIEW"
HOLD = "HOLD"
ALLOWED_RIGHTS = {"OWNED", "LICENSED_FOR_REDISTRIBUTION", "PUBLIC_DOMAIN"}
ALLOWED_SENSITIVE = {"PUBLIC", "REDACTED"}
ALLOWED_GRANTS = {"EVALUATION", "INTERNAL_USE", "COMMERCIAL_USE"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SECRET_RE = re.compile(r"(?i)(?:\bBearer\s+[A-Za-z0-9._~+/-]+=*|(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{8,})")
BLOCKED_FIELD_PARTS = {
    "email", "phone", "telephone", "mobile", "address", "street", "ssn",
    "social_security", "date_of_birth", "dob", "password", "passwd", "secret",
    "api_key", "access_token", "refresh_token", "private_key",
}
MAX_ROWS = 100
MAX_SAMPLE_BYTES = 1_000_000

class DataLicenseError(ValueError):
    pass

def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DataLicenseError(f"{field} must be UTC RFC3339 Z time")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DataLicenseError(f"{field} invalid timestamp") from exc
    if dt.tzinfo is None:
        raise DataLicenseError(f"{field} must be timezone-aware")
    return dt.astimezone(timezone.utc)

def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise DataLicenseError(f"{field} must be lowercase sha256")
    return value

def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise DataLicenseError(f"{field} invalid")
    return value

def _money(cents: int) -> str:
    if isinstance(cents, bool) or not isinstance(cents, int) or cents < 0 or cents > 9_000_000_000_000_000:
        raise DataLicenseError("offer.price_cents must be a nonnegative safe-range integer")
    return f"${cents // 100}.{cents % 100:02d}"

def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        pass
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise DataLicenseError(f"{path} contains non-finite number")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _validate_json_value(item, f"{path}[{i}]")
    elif isinstance(value, dict):
        for k, item in value.items():
            if not isinstance(k, str):
                raise DataLicenseError(f"{path} contains non-string key")
            _validate_json_value(item, f"{path}.{k}")
    else:
        raise DataLicenseError(f"{path} contains unsupported value type")
    if isinstance(value, str) and (EMAIL_RE.search(value) or SSN_RE.search(value) or SECRET_RE.search(value)):
        raise DataLicenseError(f"{path} contains PII/secret-shaped value")

def _field_safe(field: str) -> bool:
    norm = re.sub(r"[^a-z0-9]+", "_", field.lower()).strip("_")
    return not any(part == norm or part in norm.split("_") for part in BLOCKED_FIELD_PARTS)

def _zip_bytes(entries: Mapping[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            zf.writestr(info, entries[name])
    return out.getvalue()

def _offer_markdown(ds: Mapping[str, Any], evaluated_at: str) -> str:
    offer = ds["offer"]
    lines = [
        f"# Data offer: {ds['dataset_id']} / {ds['version']}",
        "",
        "**Status:** READY FOR HUMAN LICENSE REVIEW — not an executed license.",
        "",
        f"- Price: {_money(offer['price_cents'])} {offer['currency']}",
        f"- Grant requested: {offer['grant']}",
        f"- Term: {offer['term_days']} days",
        f"- Offer expires: {offer['expires_at']}",
        f"- Rights basis recorded: {ds['rights']['basis']}",
        f"- License identifier: {ds['rights']['license_id']}",
        f"- Sensitive-data class: {ds['sensitive_class']}",
        f"- Evaluated at: {evaluated_at}",
        "",
        "Human/legal review remains required before any license, transfer, publication, payment, or revenue recognition.",
        "",
    ]
    return "\n".join(lines)

def _evaluate_one(ds: Mapping[str, Any], evaluated_at: datetime, evaluated_at_raw: str) -> tuple[dict[str, Any], bytes | None]:
    reasons: list[str] = []
    try:
        dataset_id = _require_id(ds.get("dataset_id"), "dataset_id")
        version = _require_id(ds.get("version"), "version")
        source_sha = _require_sha(ds.get("source_sha256"), "source_sha256")
        prov_sha = _require_sha(ds.get("provenance_sha256"), "provenance_sha256")
        rights = ds.get("rights")
        if not isinstance(rights, dict):
            raise DataLicenseError("rights must be object")
        basis = rights.get("basis")
        if basis not in ALLOWED_RIGHTS:
            reasons.append("RIGHTS_BASIS_NOT_TRANSFERABLE_OR_UNKNOWN")
        license_id = _require_id(rights.get("license_id"), "rights.license_id")
        license_evidence_sha = _require_sha(rights.get("license_evidence_sha256"), "rights.license_evidence_sha256")
        permitted = rights.get("permitted_grants")
        if not isinstance(permitted, list) or not permitted or any(g not in ALLOWED_GRANTS for g in permitted) or len(set(permitted)) != len(permitted):
            raise DataLicenseError("rights.permitted_grants invalid")
        transfer_allowed = rights.get("transfer_allowed") is True
        if not transfer_allowed:
            reasons.append("TRANSFER_NOT_RECORDED_ALLOWED")

        sensitive_class = ds.get("sensitive_class")
        if sensitive_class not in ALLOWED_SENSITIVE:
            reasons.append("SENSITIVE_CLASS_NOT_PUBLIC_OR_REDACTED")

        red = ds.get("redaction")
        if not isinstance(red, dict):
            raise DataLicenseError("redaction must be object")
        if sensitive_class == "REDACTED":
            if red.get("status") != "VERIFIED":
                reasons.append("REDACTION_NOT_VERIFIED")
            _require_sha(red.get("policy_sha256"), "redaction.policy_sha256")
            _require_sha(red.get("review_evidence_sha256"), "redaction.review_evidence_sha256")
            reviewed = _parse_time(red.get("reviewed_at"), "redaction.reviewed_at")
            if reviewed > evaluated_at:
                reasons.append("REDACTION_REVIEW_IN_FUTURE")
        elif red.get("status") != "NOT_REQUIRED":
            reasons.append("PUBLIC_DATA_REDACTION_STATUS_INVALID")

        fields = ds.get("schema_fields")
        if not isinstance(fields, list) or not fields or any(not isinstance(x, str) or not ID_RE.fullmatch(x) for x in fields):
            raise DataLicenseError("schema_fields invalid")
        if len(set(fields)) != len(fields):
            raise DataLicenseError("schema_fields duplicate")
        if any(not _field_safe(x) for x in fields):
            reasons.append("PII_OR_SECRET_SHAPED_FIELD")

        rows = ds.get("sample_rows")
        if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
            raise DataLicenseError(f"sample_rows must contain 1..{MAX_ROWS} rows")
        field_set = set(fields)
        normalized_rows = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise DataLicenseError(f"sample_rows[{i}] must be object")
            if not set(row).issubset(field_set):
                reasons.append("SAMPLE_FIELD_OUTSIDE_SCHEMA")
            _validate_json_value(row, f"sample_rows[{i}]")
            normalized_rows.append(row)
        sample_jsonl = b"".join(canonical_json(row) for row in normalized_rows)
        if len(sample_jsonl) > MAX_SAMPLE_BYTES:
            raise DataLicenseError("sample_rows exceeds byte limit")

        offer = ds.get("offer")
        if not isinstance(offer, dict):
            raise DataLicenseError("offer must be object")
        if offer.get("currency") != "USD":
            reasons.append("UNSUPPORTED_CURRENCY")
        _money(offer.get("price_cents"))
        grant = offer.get("grant")
        if grant not in ALLOWED_GRANTS:
            raise DataLicenseError("offer.grant invalid")
        if grant not in permitted:
            reasons.append("OFFER_GRANT_NOT_PERMITTED_BY_RIGHTS")
        term_days = offer.get("term_days")
        if isinstance(term_days, bool) or not isinstance(term_days, int) or not (1 <= term_days <= 3650):
            raise DataLicenseError("offer.term_days invalid")
        expires = _parse_time(offer.get("expires_at"), "offer.expires_at")
        if expires <= evaluated_at:
            reasons.append("OFFER_EXPIRED")

        meta = {
            "schema": "commons-data-sample-pack/v1",
            "dataset_id": dataset_id,
            "version": version,
            "source_sha256": source_sha,
            "provenance_sha256": prov_sha,
            "license_id": license_id,
            "license_evidence_sha256": license_evidence_sha,
            "rights_basis": basis,
            "permitted_grants": permitted,
            "rights": {
                "basis": basis,
                "license_id": license_id,
                "license_evidence_sha256": license_evidence_sha,
                "permitted_grants": permitted,
                "transfer_allowed": transfer_allowed,
            },
            "sensitive_class": sensitive_class,
            "redaction": red,
            "schema_fields": fields,
            "sample_rows": len(rows),
            "sample_jsonl_sha256": sha256(sample_jsonl),
        }
        status = READY if not reasons else HOLD
        pack = None
        pack_sha = None
        if status == READY:
            offer_md = _offer_markdown(ds, evaluated_at_raw).encode("utf-8")
            pack = _zip_bytes({
                "manifest.json": canonical_json(meta),
                "sample.jsonl": sample_jsonl,
                "OFFER.md": offer_md,
            })
            pack_sha = sha256(pack)
        result = {
            "dataset_id": dataset_id,
            "version": version,
            "status": status,
            "reasons": sorted(set(reasons)),
            "source_sha256": source_sha,
            "provenance_sha256": prov_sha,
            "license_evidence_sha256": license_evidence_sha,
            "rights": {
                "basis": basis,
                "license_id": license_id,
                "permitted_grants": permitted,
                "transfer_allowed": transfer_allowed,
            },
            "sensitive_class": sensitive_class,
            "redaction": red,
            "sample_jsonl_sha256": sha256(sample_jsonl),
            "sample_pack_sha256": pack_sha,
            "offer": {
                "currency": offer["currency"],
                "price_cents": offer["price_cents"],
                "grant": grant,
                "term_days": term_days,
                "expires_at": offer["expires_at"],
            },
            "authority": {
                "human_license_review_ready": status == READY,
                "license_executed": False,
                "transfer_authorized": False,
                "publication_authorized": False,
                "payment_authorized": False,
                "revenue_recognized": False,
            },
        }
        return result, pack
    except DataLicenseError as exc:
        dataset_id = ds.get("dataset_id") if isinstance(ds.get("dataset_id"), str) else "<invalid>"
        return {
            "dataset_id": dataset_id,
            "version": ds.get("version") if isinstance(ds.get("version"), str) else "<invalid>",
            "status": HOLD,
            "reasons": [f"MALFORMED:{exc}"],
            "sample_pack_sha256": None,
            "authority": {
                "human_license_review_ready": False,
                "license_executed": False,
                "transfer_authorized": False,
                "publication_authorized": False,
                "payment_authorized": False,
                "revenue_recognized": False,
            },
        }, None

def build_catalog(document: Mapping[str, Any], trusted_at: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise DataLicenseError(f"schema must be {SCHEMA}")
    evaluated_at_raw = trusted_at
    evaluated_at = _parse_time(evaluated_at_raw, "trusted_at")
    datasets = document.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise DataLicenseError("datasets must be a nonempty list")
    ids = [d.get("dataset_id") for d in datasets if isinstance(d, dict)]
    if len(ids) != len(datasets) or len(set(ids)) != len(ids):
        raise DataLicenseError("dataset_id must be present and unique")
    rows = []
    packs: dict[str, bytes] = {}
    for ds in datasets:
        row, pack = _evaluate_one(ds, evaluated_at, evaluated_at_raw)
        rows.append(row)
        if pack is not None:
            packs[row["dataset_id"]] = pack
    decision = READY if rows and all(r["status"] == READY for r in rows) else HOLD
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "evaluated_at": evaluated_at_raw,
        "decision": decision,
        "datasets": rows,
        "authority": {
            "human_license_review_ready": decision == READY,
            "license_executed": False,
            "transfer_authorized": False,
            "publication_authorized": False,
            "payment_authorized": False,
            "revenue_recognized": False,
        },
    }
    receipt["receipt_sha256"] = sha256(canonical_json(receipt))
    return receipt, packs

def verify_catalog(document: Mapping[str, Any], receipt: Mapping[str, Any], packs: Mapping[str, bytes], trusted_at: str) -> bool:
    expected, expected_packs = build_catalog(document, trusted_at)
    if canonical_json(expected) != canonical_json(receipt):
        return False
    if set(packs) != set(expected_packs):
        return False
    for dataset_id, payload in expected_packs.items():
        if packs.get(dataset_id) != payload:
            return False
        expected_sha = next(r["sample_pack_sha256"] for r in expected["datasets"] if r["dataset_id"] == dataset_id)
        if sha256(payload) != expected_sha:
            return False
    return True
