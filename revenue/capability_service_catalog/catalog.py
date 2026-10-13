from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA = "commons-capability-service-catalog-input/v1"
PACKAGE_SCHEMA = "commons-capability-service-catalog-package/v1"
RECEIPT_SCHEMA = "commons-capability-service-catalog-receipt/v1"
READY = "READY_FOR_HUMAN_SERVICE_CATALOG_REVIEW"
HOLD = "HOLD"

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|rk|pk)-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}\b", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_ALLOWED_MODES = {"ASSESSMENT", "IMPLEMENTATION", "RECOVERY", "VALIDATION", "TRAINING", "ADVISORY"}
_ALLOWED_FORMATS = {
    "WRITTEN_ASSESSMENT",
    "IMPLEMENTATION_SPRINT",
    "RECOVERY_SPRINT",
    "VALIDATION_PACKET",
    "TRAINING_SESSION",
    "ADVISORY_SESSION",
    "EMBEDDED_ENGAGEMENT",
}


class CatalogError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CatalogError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(raw: str) -> dict[str, Any]:
    try:
        obj = json.loads(
            raw,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=lambda value: (_ for _ in ()).throw(CatalogError(f"non-finite JSON number: {value}")),
        )
    except CatalogError:
        raise
    except json.JSONDecodeError as exc:
        raise CatalogError(f"invalid JSON: {exc.msg}") from exc
    if type(obj) is not dict:
        raise CatalogError("top-level JSON must be an object")
    return obj


def dumps_canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(dumps_canonical(value).encode("utf-8")).hexdigest()


def _exact_dict(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CatalogError(f"{where} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise CatalogError(f"{where} schema mismatch missing={missing} extra={extra}")
    return value


def _exact_dict_optional(value: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CatalogError(f"{where} must be an object")
    actual = set(value)
    missing = required - actual
    extra = actual - required - optional
    if missing or extra:
        raise CatalogError(f"{where} schema mismatch missing={sorted(missing)} extra={sorted(extra)}")
    return value


def _str(value: Any, where: str, *, max_len: int = 4000) -> str:
    if type(value) is not str:
        raise CatalogError(f"{where} must be a string")
    if not value or value != value.strip() or len(value) > max_len:
        raise CatalogError(f"{where} must be nonblank, trimmed, and <= {max_len} chars")
    _reject_sensitive(value, where)
    return value


def _identifier(value: Any, where: str) -> str:
    text = _str(value, where, max_len=80)
    if not _ID.fullmatch(text):
        raise CatalogError(f"{where} must match {_ID.pattern}")
    return text


def _reject_sensitive(text: str, where: str) -> None:
    if _EMAIL.search(text):
        raise CatalogError(f"{where} contains email-shaped PII")
    if _SSN.search(text):
        raise CatalogError(f"{where} contains SSN-shaped PII")
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise CatalogError(f"{where} contains secret-shaped material")


def _utc(value: Any, where: str) -> datetime:
    text = _str(value, where, max_len=32)
    if not text.endswith("Z"):
        raise CatalogError(f"{where} must be UTC Z time")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise CatalogError(f"{where} invalid timestamp") from exc
    if dt.tzinfo != timezone.utc:
        raise CatalogError(f"{where} must be UTC")
    if dt.microsecond:
        raise CatalogError(f"{where} must use whole seconds")
    return dt


def _utc_text(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _int(value: Any, where: str, *, minimum: int = 0, maximum: int = 9_007_199_254_740_991) -> int:
    if type(value) is not int:
        raise CatalogError(f"{where} must be an integer")
    if value < minimum or value > maximum:
        raise CatalogError(f"{where} outside [{minimum}, {maximum}]")
    return value


def _list(value: Any, where: str, *, minimum: int = 0) -> list[Any]:
    if type(value) is not list:
        raise CatalogError(f"{where} must be an array")
    if len(value) < minimum:
        raise CatalogError(f"{where} must contain at least {minimum} item(s)")
    return value


def _unique_strings(values: Any, where: str, *, minimum: int = 0, max_len: int = 4000) -> list[str]:
    items = _list(values, where, minimum=minimum)
    out = [_str(item, f"{where}[{i}]", max_len=max_len) for i, item in enumerate(items)]
    if len(set(out)) != len(out):
        raise CatalogError(f"{where} contains duplicates")
    return out


def _validate_source(value: Any, where: str) -> dict[str, str]:
    source = _exact_dict(value, {"repo", "commit", "path", "sha256"}, where)
    repo = _str(source["repo"], f"{where}.repo", max_len=200)
    if repo.count("/") != 1 or repo.startswith("/") or repo.endswith("/"):
        raise CatalogError(f"{where}.repo must be owner/name")
    commit = _str(source["commit"], f"{where}.commit", max_len=40)
    if not _HEX40.fullmatch(commit):
        raise CatalogError(f"{where}.commit must be an immutable 40-hex SHA")
    path = _str(source["path"], f"{where}.path", max_len=500)
    if path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise CatalogError(f"{where}.path must be a normalized repository-relative path")
    sha256 = _str(source["sha256"], f"{where}.sha256", max_len=64)
    if not _HEX64.fullmatch(sha256):
        raise CatalogError(f"{where}.sha256 must be 64 lowercase hex")
    return {"repo": repo, "commit": commit, "path": path, "sha256": sha256}


def _validate_evidence(value: Any, where: str) -> dict[str, str]:
    evidence = _exact_dict(value, {"observed_at", "outcome", "verification", "receipt_sha256"}, where)
    observed = _utc(evidence["observed_at"], f"{where}.observed_at")
    receipt = _str(evidence["receipt_sha256"], f"{where}.receipt_sha256", max_len=64)
    if not _HEX64.fullmatch(receipt):
        raise CatalogError(f"{where}.receipt_sha256 must be 64 lowercase hex")
    return {
        "observed_at": _utc_text(observed),
        "outcome": _str(evidence["outcome"], f"{where}.outcome", max_len=600),
        "verification": _str(evidence["verification"], f"{where}.verification", max_len=600),
        "receipt_sha256": receipt,
    }


def _validate_capability(value: Any, where: str) -> dict[str, Any]:
    cap = _exact_dict(value, {"capability_id", "name", "source", "evidence", "allowed_service_modes"}, where)
    modes = _unique_strings(cap["allowed_service_modes"], f"{where}.allowed_service_modes", minimum=1, max_len=32)
    unknown = sorted(set(modes) - _ALLOWED_MODES)
    if unknown:
        raise CatalogError(f"{where}.allowed_service_modes unsupported={unknown}")
    return {
        "capability_id": _identifier(cap["capability_id"], f"{where}.capability_id"),
        "name": _str(cap["name"], f"{where}.name", max_len=160),
        "source": _validate_source(cap["source"], f"{where}.source"),
        "evidence": _validate_evidence(cap["evidence"], f"{where}.evidence"),
        "allowed_service_modes": sorted(modes),
    }


def _validate_deliverable(value: Any, where: str) -> dict[str, Any]:
    item = _exact_dict(value, {"deliverable_id", "description", "acceptance_criteria"}, where)
    criteria = _unique_strings(item["acceptance_criteria"], f"{where}.acceptance_criteria", minimum=1, max_len=600)
    return {
        "deliverable_id": _identifier(item["deliverable_id"], f"{where}.deliverable_id"),
        "description": _str(item["description"], f"{where}.description", max_len=600),
        "acceptance_criteria": sorted(criteria),
    }


def _validate_commercial(value: Any, where: str) -> dict[str, Any]:
    commercial = _exact_dict_optional(value, {"mode"}, {"currency", "minor_units"}, where)
    mode = _str(commercial["mode"], f"{where}.mode", max_len=32)
    if mode == "UNPRICED_SCOPE_REVIEW":
        if set(commercial) != {"mode"}:
            raise CatalogError(f"{where}: UNPRICED_SCOPE_REVIEW cannot carry price fields")
        return {"mode": mode}
    if mode != "FIXED":
        raise CatalogError(f"{where}.mode must be FIXED or UNPRICED_SCOPE_REVIEW")
    if set(commercial) != {"mode", "currency", "minor_units"}:
        raise CatalogError(f"{where}: FIXED requires currency and minor_units")
    currency = _str(commercial["currency"], f"{where}.currency", max_len=3)
    if not _CURRENCY.fullmatch(currency):
        raise CatalogError(f"{where}.currency must be ISO-like 3 uppercase letters")
    minor_units = _int(commercial["minor_units"], f"{where}.minor_units", minimum=1)
    return {"mode": mode, "currency": currency, "minor_units": minor_units}


def _service_core(raw: dict[str, Any], where: str) -> dict[str, Any]:
    required = {
        "service_id",
        "title",
        "service_mode",
        "delivery_format",
        "capability_ids",
        "deliverables",
        "exclusions",
        "dependencies",
        "commercial",
    }
    core_raw = _exact_dict(raw, required, where)
    service_mode = _str(core_raw["service_mode"], f"{where}.service_mode", max_len=32)
    if service_mode not in _ALLOWED_MODES:
        raise CatalogError(f"{where}.service_mode unsupported")
    delivery_format = _str(core_raw["delivery_format"], f"{where}.delivery_format", max_len=40)
    if delivery_format not in _ALLOWED_FORMATS:
        raise CatalogError(f"{where}.delivery_format unsupported")
    capability_ids = [_identifier(v, f"{where}.capability_ids[{i}]") for i, v in enumerate(_list(core_raw["capability_ids"], f"{where}.capability_ids", minimum=1))]
    if len(set(capability_ids)) != len(capability_ids):
        raise CatalogError(f"{where}.capability_ids contains duplicates")
    deliverables = [_validate_deliverable(v, f"{where}.deliverables[{i}]") for i, v in enumerate(_list(core_raw["deliverables"], f"{where}.deliverables", minimum=1))]
    ids = [d["deliverable_id"] for d in deliverables]
    if len(set(ids)) != len(ids):
        raise CatalogError(f"{where}.deliverables has duplicate deliverable_id")
    exclusions = _unique_strings(core_raw["exclusions"], f"{where}.exclusions", minimum=1, max_len=600)
    dependencies = _unique_strings(core_raw["dependencies"], f"{where}.dependencies", minimum=0, max_len=300)
    return {
        "service_id": _identifier(core_raw["service_id"], f"{where}.service_id"),
        "title": _str(core_raw["title"], f"{where}.title", max_len=160),
        "service_mode": service_mode,
        "delivery_format": delivery_format,
        "capability_ids": sorted(capability_ids),
        "deliverables": sorted(deliverables, key=lambda x: x["deliverable_id"]),
        "exclusions": sorted(exclusions),
        "dependencies": sorted(dependencies),
        "commercial": _validate_commercial(core_raw["commercial"], f"{where}.commercial"),
    }


def mapping_sha256(mapping: dict[str, Any]) -> str:
    """Return the canonical digest an owner approval must bind.

    The digest commits to the validated, normalized service mapping rather than
    incidental JSON/list ordering. Invalid mappings fail closed.
    """
    return _digest(_service_core(deepcopy(mapping), "mapping"))


def _validate_approval(value: Any, where: str) -> dict[str, str]:
    approval = _exact_dict(value, {"ref", "approved_at", "valid_until", "mapping_sha256"}, where)
    approved = _utc(approval["approved_at"], f"{where}.approved_at")
    valid_until = _utc(approval["valid_until"], f"{where}.valid_until")
    if valid_until <= approved:
        raise CatalogError(f"{where}.valid_until must be after approved_at")
    mapping = _str(approval["mapping_sha256"], f"{where}.mapping_sha256", max_len=64)
    if not _HEX64.fullmatch(mapping):
        raise CatalogError(f"{where}.mapping_sha256 must be 64 lowercase hex")
    return {
        "ref": _str(approval["ref"], f"{where}.ref", max_len=300),
        "approved_at": _utc_text(approved),
        "valid_until": _utc_text(valid_until),
        "mapping_sha256": mapping,
    }


def _normalize(doc: dict[str, Any]) -> dict[str, Any]:
    top = _exact_dict(doc, {"schema", "capabilities", "services"}, "root")
    if top["schema"] != SCHEMA:
        raise CatalogError(f"root.schema must equal {SCHEMA}")
    caps = [_validate_capability(v, f"capabilities[{i}]") for i, v in enumerate(_list(top["capabilities"], "capabilities", minimum=1))]
    cap_ids = [c["capability_id"] for c in caps]
    if len(set(cap_ids)) != len(cap_ids):
        raise CatalogError("duplicate capability_id")

    services: list[dict[str, Any]] = []
    raw_services = _list(top["services"], "services", minimum=1)
    for i, raw in enumerate(raw_services):
        container = _exact_dict(raw, {"mapping", "owner_approval"}, f"services[{i}]")
        core = _service_core(container["mapping"], f"services[{i}].mapping")
        approval = _validate_approval(container["owner_approval"], f"services[{i}].owner_approval")
        services.append({"mapping": core, "owner_approval": approval})
    service_ids = [s["mapping"]["service_id"] for s in services]
    if len(set(service_ids)) != len(service_ids):
        raise CatalogError("duplicate service_id")
    return {
        "schema": SCHEMA,
        "capabilities": sorted(caps, key=lambda x: x["capability_id"]),
        "services": sorted(services, key=lambda x: x["mapping"]["service_id"]),
    }


def compile_catalog(doc: dict[str, Any], *, as_of: str, max_evidence_age_days: int = 90) -> dict[str, Any]:
    if type(max_evidence_age_days) is not int or max_evidence_age_days < 1 or max_evidence_age_days > 3650:
        raise CatalogError("max_evidence_age_days must be integer in [1,3650]")
    as_of_dt = _utc(as_of, "as_of")
    normalized = _normalize(deepcopy(doc))
    cap_by_id = {c["capability_id"]: c for c in normalized["capabilities"]}
    reasons: set[str] = set()
    catalog_services: list[dict[str, Any]] = []
    covered: set[str] = set()

    for cap in normalized["capabilities"]:
        observed = _utc(cap["evidence"]["observed_at"], f"capability {cap['capability_id']} observed_at")
        if observed > as_of_dt:
            reasons.add("CAPABILITY_EVIDENCE_FROM_FUTURE")
        if as_of_dt - observed > timedelta(days=max_evidence_age_days):
            reasons.add("CAPABILITY_EVIDENCE_STALE")

    for service in normalized["services"]:
        mapping = service["mapping"]
        approval = service["owner_approval"]
        sid = mapping["service_id"]
        mapping_digest = _digest(mapping)
        if approval["mapping_sha256"] != mapping_digest:
            reasons.add("OWNER_APPROVAL_MAPPING_DIGEST_MISMATCH")
        approved_dt = _utc(approval["approved_at"], f"{sid}.approved_at")
        valid_until = _utc(approval["valid_until"], f"{sid}.valid_until")
        if approved_dt > as_of_dt:
            reasons.add("OWNER_APPROVAL_FROM_FUTURE")
        if as_of_dt > valid_until:
            reasons.add("OWNER_APPROVAL_EXPIRED")

        capability_evidence_times: list[datetime] = []
        for cap_id in mapping["capability_ids"]:
            cap = cap_by_id.get(cap_id)
            if cap is None:
                reasons.add("SERVICE_REFERENCES_UNKNOWN_CAPABILITY")
                continue
            covered.add(cap_id)
            capability_evidence_times.append(_utc(cap["evidence"]["observed_at"], f"{sid}.{cap_id}.observed_at"))
            if mapping["service_mode"] not in cap["allowed_service_modes"]:
                reasons.add("CAPABILITY_MODE_NOT_AUTHORIZED")
        if capability_evidence_times and approved_dt < max(capability_evidence_times):
            reasons.add("OWNER_APPROVAL_PREDATES_CAPABILITY_EVIDENCE")

        service_row = deepcopy(mapping)
        service_row["mapping_sha256"] = mapping_digest
        service_row["owner_approval"] = approval
        catalog_services.append(service_row)

    uncovered = sorted(set(cap_by_id) - covered)
    if uncovered:
        reasons.add("DEMONSTRATED_CAPABILITY_UNCOVERED")

    reason_list = sorted(reasons)
    status = HOLD if reason_list else READY
    catalog = {
        "schema": "commons-capability-service-catalog/v1",
        "as_of": _utc_text(as_of_dt),
        "max_evidence_age_days": max_evidence_age_days,
        "status": status,
        "reason_codes": reason_list,
        "capability_count": len(normalized["capabilities"]),
        "service_count": len(catalog_services),
        "covered_capability_ids": sorted(covered),
        "uncovered_capability_ids": uncovered,
        "services": sorted(catalog_services, key=lambda x: x["service_id"]),
        "authority": {
            "catalog_publication_authorized": False,
            "buyer_contact_authorized": False,
            "offer_send_authorized": False,
            "contract_execution_authorized": False,
            "fulfillment_authorized": False,
            "checkout_or_payment_authorized": False,
            "buyer_acceptance_asserted": False,
            "cash_or_revenue_asserted": False,
        },
    }
    input_digest = _digest(normalized)
    catalog_digest = _digest(catalog)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "input_sha256": input_digest,
        "catalog_sha256": catalog_digest,
        "as_of": _utc_text(as_of_dt),
        "max_evidence_age_days": max_evidence_age_days,
        "status": status,
        "reason_codes": reason_list,
        "capability_count": len(normalized["capabilities"]),
        "service_count": len(catalog_services),
        "side_effects_authorized": False,
    }
    receipt["receipt_sha256"] = _digest(receipt)
    return {"schema": PACKAGE_SCHEMA, "catalog": catalog, "receipt": receipt}


def verify_package(doc: dict[str, Any], package: dict[str, Any], *, as_of: str, max_evidence_age_days: int = 90) -> bool:
    try:
        pkg = _exact_dict(package, {"schema", "catalog", "receipt"}, "package")
        if pkg["schema"] != PACKAGE_SCHEMA:
            return False
        receipt = _exact_dict(
            pkg["receipt"],
            {"schema", "input_sha256", "catalog_sha256", "as_of", "max_evidence_age_days", "status", "reason_codes", "capability_count", "service_count", "side_effects_authorized", "receipt_sha256"},
            "receipt",
        )
        if receipt["schema"] != RECEIPT_SCHEMA or receipt["side_effects_authorized"] is not False:
            return False
        supplied_sha = receipt["receipt_sha256"]
        if type(supplied_sha) is not str or not _HEX64.fullmatch(supplied_sha):
            return False
        base = dict(receipt)
        del base["receipt_sha256"]
        if _digest(base) != supplied_sha:
            return False
        expected = compile_catalog(doc, as_of=as_of, max_evidence_age_days=max_evidence_age_days)
        return dumps_canonical(expected) == dumps_canonical(package)
    except (CatalogError, TypeError, ValueError, OverflowError):
        return False


def render_csv(package: dict[str, Any]) -> str:
    catalog = package["catalog"]
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "service_id",
        "title",
        "service_mode",
        "delivery_format",
        "capability_ids",
        "commercial_mode",
        "currency",
        "minor_units",
        "deliverable_ids",
        "mapping_sha256",
        "approval_ref",
        "approval_valid_until",
        "catalog_status",
    ])
    for service in catalog["services"]:
        commercial = service["commercial"]
        writer.writerow([
            service["service_id"],
            service["title"],
            service["service_mode"],
            service["delivery_format"],
            ";".join(service["capability_ids"]),
            commercial["mode"],
            commercial.get("currency", ""),
            commercial.get("minor_units", ""),
            ";".join(d["deliverable_id"] for d in service["deliverables"]),
            service["mapping_sha256"],
            service["owner_approval"]["ref"],
            service["owner_approval"]["valid_until"],
            catalog["status"],
        ])
    return output.getvalue()


def render_markdown(package: dict[str, Any]) -> str:
    catalog = package["catalog"]
    lines = [
        "# Capability-backed service catalog",
        "",
        f"Status: `{catalog['status']}`",
        f"As of: `{catalog['as_of']}`",
        f"Capability coverage: `{len(catalog['covered_capability_ids'])}/{catalog['capability_count']}`",
    ]
    if catalog["reason_codes"]:
        lines += ["", "## Holds", ""] + [f"- `{code}`" for code in catalog["reason_codes"]]
    for service in catalog["services"]:
        lines += [
            "",
            f"## {service['title']}",
            "",
            f"- Service ID: `{service['service_id']}`",
            f"- Mode: `{service['service_mode']}`",
            f"- Delivery format: `{service['delivery_format']}`",
            f"- Capabilities: {', '.join(f'`{x}`' for x in service['capability_ids'])}",
            f"- Mapping digest: `{service['mapping_sha256']}`",
            f"- Owner approval: `{service['owner_approval']['ref']}` through `{service['owner_approval']['valid_until']}`",
        ]
        commercial = service["commercial"]
        if commercial["mode"] == "FIXED":
            lines.append(f"- Commercial: `FIXED {commercial['currency']} {commercial['minor_units']} minor units`")
        else:
            lines.append("- Commercial: `UNPRICED_SCOPE_REVIEW`")
        lines += ["", "### Deliverables", ""]
        for deliverable in service["deliverables"]:
            lines.append(f"- **{deliverable['deliverable_id']}** — {deliverable['description']}")
            for criterion in deliverable["acceptance_criteria"]:
                lines.append(f"  - Acceptance: {criterion}")
        lines += ["", "### Exclusions", ""] + [f"- {item}" for item in service["exclusions"]]
        if service["dependencies"]:
            lines += ["", "### Dependencies", ""] + [f"- {item}" for item in service["dependencies"]]
    lines += [
        "",
        "## Authority boundary",
        "",
        "This artifact is review evidence only. It does not publish a catalog entry, contact a buyer, send an offer, execute a contract, fulfill work, move money, assert buyer acceptance, or recognize cash/revenue.",
        "",
    ]
    return "\n".join(lines)
