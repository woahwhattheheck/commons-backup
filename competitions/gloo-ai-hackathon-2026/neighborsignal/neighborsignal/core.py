from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any

from .canonical import CanonicalError, sha256_hex

POLICY_VERSION = "neighborsignal-policy/v1"
REQUEST_SCHEMA = "neighborsignal.care-request/v1"
CATALOG_SCHEMA = "neighborsignal.resource-catalog/v1"
PLAN_SCHEMA = "neighborsignal.care-plan/v1"
RECEIPT_SCHEMA = "neighborsignal.receipt/v1"

_ALLOWED_NEEDS = {"FOOD", "TRANSPORT", "UTILITY", "TEMPORARY_HOUSING", "GENERAL"}
_ALLOWED_URGENCY = {"ROUTINE", "SOON", "URGENT"}
_ALLOWED_RESOURCE_STATUS = {"ACTIVE", "PAUSED"}
_HIGH_AUTHORITY_NEEDS = {"UTILITY", "TEMPORARY_HOUSING"}
_FORBIDDEN_FIELD_PARTS = {
    "email", "phone", "mobile", "address", "street", "ssn", "social_security", "date_of_birth",
    "dob", "password", "secret", "token", "api_key", "apikey", "credential", "credit_card", "bank_account"
}
_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,95}$")


class PolicyError(ValueError):
    pass


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{name} must be an object")
    return value


def _require_str(obj: dict[str, Any], key: str, *, max_len: int = 500) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise PolicyError(f"{key} must be a non-empty string <= {max_len} chars")
    return value


def _require_id(obj: dict[str, Any], key: str) -> str:
    value = _require_str(obj, key, max_len=96)
    if not _ID_RE.fullmatch(value):
        raise PolicyError(f"{key} has invalid identifier syntax")
    return value


def _parse_ts(value: str, key: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PolicyError(f"{key} must be an RFC3339 UTC timestamp ending in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PolicyError(f"{key} is not a valid RFC3339 timestamp") from exc
    if dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise PolicyError(f"{key} must be UTC")
    return dt


def _fmt_ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise PolicyError("evaluation time must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scan_for_forbidden_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            folded = key.lower().replace("-", "_")
            if any(part in folded for part in _FORBIDDEN_FIELD_PARTS):
                raise PolicyError(f"privacy boundary rejects field {path}.{key}")
            _scan_for_forbidden_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _scan_for_forbidden_fields(child, f"{path}[{i}]")


def _validate_request(raw: Any, evaluated_at: datetime) -> dict[str, Any]:
    req = deepcopy(_require_object(raw, "request"))
    if set(req) != {"schema", "case_id", "captured_at", "need_type", "urgency", "summary", "facts"}:
        raise PolicyError("request keys must exactly match the v1 schema")
    if req["schema"] != REQUEST_SCHEMA:
        raise PolicyError("unsupported request schema")
    _require_id(req, "case_id")
    captured = _parse_ts(_require_str(req, "captured_at", max_len=40), "request.captured_at")
    if captured > evaluated_at:
        raise PolicyError("request was captured in the future")
    if req["need_type"] not in _ALLOWED_NEEDS:
        raise PolicyError("unsupported need_type")
    if req["urgency"] not in _ALLOWED_URGENCY:
        raise PolicyError("unsupported urgency")
    _require_str(req, "summary", max_len=500)
    facts = req["facts"]
    if not isinstance(facts, list) or len(facts) > 32:
        raise PolicyError("facts must be a list of at most 32 entries")
    seen = set()
    for index, fact in enumerate(facts):
        fact = _require_object(fact, f"facts[{index}]")
        if set(fact) != {"key", "value", "source_ref", "captured_at"}:
            raise PolicyError("fact keys must exactly match the v1 schema")
        key = _require_id(fact, "key")
        if key in seen:
            raise PolicyError(f"duplicate fact key: {key}")
        seen.add(key)
        value = fact["value"]
        if not isinstance(value, (str, bool, int)) or isinstance(value, float):
            raise PolicyError(f"fact {key} value must be string/bool/int")
        if isinstance(value, str) and len(value) > 160:
            raise PolicyError(f"fact {key} value too long")
        _require_id(fact, "source_ref")
        fts = _parse_ts(_require_str(fact, "captured_at", max_len=40), f"fact {key}.captured_at")
        if fts > captured:
            raise PolicyError(f"fact {key} postdates request capture")
    _scan_for_forbidden_fields(req)
    return req


def _validate_catalog(raw: Any, evaluated_at: datetime) -> dict[str, Any]:
    catalog = deepcopy(_require_object(raw, "catalog"))
    if set(catalog) != {"schema", "catalog_id", "captured_at", "valid_until", "resources"}:
        raise PolicyError("catalog keys must exactly match the v1 schema")
    if catalog["schema"] != CATALOG_SCHEMA:
        raise PolicyError("unsupported catalog schema")
    _require_id(catalog, "catalog_id")
    captured = _parse_ts(_require_str(catalog, "captured_at", max_len=40), "catalog.captured_at")
    if captured > evaluated_at:
        raise PolicyError("catalog was captured in the future")
    valid_until = _parse_ts(_require_str(catalog, "valid_until", max_len=40), "catalog.valid_until")
    if valid_until < captured:
        raise PolicyError("catalog.valid_until precedes catalog.captured_at")
    resources = catalog["resources"]
    if not isinstance(resources, list) or len(resources) > 256:
        raise PolicyError("resources must be a list of at most 256 rows")
    seen = set()
    for index, resource in enumerate(resources):
        resource = _require_object(resource, f"resources[{index}]")
        expected = {"resource_id", "name", "need_types", "status", "capacity", "expires_at", "volunteer_safe", "requirements", "evidence_ref"}
        if set(resource) != expected:
            raise PolicyError(f"resource keys must exactly match the v1 schema: {sorted(expected)}")
        rid = _require_id(resource, "resource_id")
        if rid in seen:
            raise PolicyError(f"duplicate resource_id: {rid}")
        seen.add(rid)
        _require_str(resource, "name", max_len=120)
        nts = resource["need_types"]
        if not isinstance(nts, list) or not nts or any(nt not in _ALLOWED_NEEDS for nt in nts) or len(set(nts)) != len(nts):
            raise PolicyError(f"resource {rid} need_types invalid")
        if resource["status"] not in _ALLOWED_RESOURCE_STATUS:
            raise PolicyError(f"resource {rid} status invalid")
        if not isinstance(resource["capacity"], int) or isinstance(resource["capacity"], bool) or not (0 <= resource["capacity"] <= 1_000_000):
            raise PolicyError(f"resource {rid} capacity invalid")
        _parse_ts(_require_str(resource, "expires_at", max_len=40), f"resource {rid}.expires_at")
        if not isinstance(resource["volunteer_safe"], bool):
            raise PolicyError(f"resource {rid} volunteer_safe must be bool")
        requirements = resource["requirements"]
        if not isinstance(requirements, list) or len(requirements) > 16:
            raise PolicyError(f"resource {rid} requirements invalid")
        req_seen = set()
        for req in requirements:
            req = _require_object(req, f"resource {rid} requirement")
            if set(req) != {"fact_key", "equals"}:
                raise PolicyError(f"resource {rid} requirement keys invalid")
            fk = _require_id(req, "fact_key")
            if fk in req_seen:
                raise PolicyError(f"resource {rid} duplicate requirement for {fk}")
            req_seen.add(fk)
            if not isinstance(req["equals"], (str, bool, int)) or isinstance(req["equals"], float):
                raise PolicyError(f"resource {rid} requirement value invalid")
        _require_id(resource, "evidence_ref")
    _scan_for_forbidden_fields(catalog)
    return catalog


def _facts_map(req: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in req["facts"]}


def _compile(req: dict[str, Any], catalog: dict[str, Any], evaluated_at: datetime) -> dict[str, Any]:
    facts = _facts_map(req)
    reasons: list[str] = []
    recommendations: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    eval_s = _fmt_ts(evaluated_at)
    catalog_expired = _parse_ts(catalog["valid_until"], "catalog.valid_until") < evaluated_at
    if catalog_expired:
        reasons.append("CATALOG_EXPIRED")

    for resource in sorted(catalog["resources"], key=lambda r: r["resource_id"]):
        if req["need_type"] not in resource["need_types"]:
            continue
        resource_reasons: list[str] = []
        expires = _parse_ts(resource["expires_at"], f"resource {resource['resource_id']}.expires_at")
        if resource["status"] != "ACTIVE":
            resource_reasons.append("RESOURCE_PAUSED")
        if resource["capacity"] <= 0:
            resource_reasons.append("NO_DECLARED_CAPACITY")
        if expires < evaluated_at:
            resource_reasons.append("RESOURCE_EXPIRED")
        if catalog_expired:
            resource_reasons.append("CATALOG_EXPIRED")
        missing: list[str] = []
        mismatched: list[str] = []
        evidence = [resource["evidence_ref"]]
        for requirement in resource["requirements"]:
            fact = facts.get(requirement["fact_key"])
            if fact is None:
                missing.append(requirement["fact_key"])
            elif fact["value"] != requirement["equals"]:
                mismatched.append(requirement["fact_key"])
                evidence.append(fact["source_ref"])
            else:
                evidence.append(fact["source_ref"])
        if missing:
            resource_reasons.append("MISSING_EXPLICIT_FACT:" + ",".join(sorted(missing)))
        if mismatched:
            resource_reasons.append("REQUIREMENT_MISMATCH:" + ",".join(sorted(mismatched)))
        matched = not resource_reasons
        rec_state = "ELIGIBLE_FOR_OWNER_REVIEW" if matched else "NOT_ELIGIBLE_FROM_CURRENT_EVIDENCE"
        recommendations.append({
            "resource_id": resource["resource_id"],
            "name": resource["name"],
            "state": rec_state,
            "reasons": sorted(resource_reasons),
            "evidence_refs": sorted(set(evidence)),
        })
        if matched:
            actions.append({
                "action_id": f"info:{resource['resource_id']}",
                "class": "INFORMATION_ONLY",
                "resource_id": resource["resource_id"],
                "instruction": f"Present {resource['name']} to an authorized human for review.",
                "external_execution_authorized": False,
                "evidence_refs": sorted(set(evidence)),
            })
            if resource["volunteer_safe"] and req["need_type"] not in _HIGH_AUTHORITY_NEEDS:
                actions.append({
                    "action_id": f"volunteer:{resource['resource_id']}",
                    "class": "VOLUNTEER_TASK_DRAFT",
                    "resource_id": resource["resource_id"],
                    "instruction": "Draft an internal volunteer handoff; a human must approve scope and contact separately.",
                    "external_execution_authorized": False,
                    "evidence_refs": sorted(set(evidence)),
                })
            else:
                actions.append({
                    "action_id": f"review:{resource['resource_id']}",
                    "class": "OWNER_REVIEW",
                    "resource_id": resource["resource_id"],
                    "instruction": "Owner review required before any commitment, funds, housing, utility, or external contact action.",
                    "external_execution_authorized": False,
                    "evidence_refs": sorted(set(evidence)),
                })

    eligible = [r for r in recommendations if r["state"] == "ELIGIBLE_FOR_OWNER_REVIEW"]
    if catalog_expired:
        authority = "HOLD"
    elif not eligible:
        authority = "OWNER_REVIEW"
        reasons.append("NO_CURRENTLY_ELIGIBLE_RESOURCE")
    elif req["need_type"] in _HIGH_AUTHORITY_NEEDS:
        authority = "OWNER_REVIEW"
        reasons.append("HIGH_AUTHORITY_NEED_REQUIRES_OWNER")
    else:
        authority = "OWNER_REVIEW"
    if req["urgency"] == "URGENT":
        reasons.append("URGENT_LABEL_DOES_NOT_EXPAND_AUTHORITY")

    plan_core = {
        "schema": PLAN_SCHEMA,
        "policy_version": POLICY_VERSION,
        "case_id": req["case_id"],
        "evaluated_at": eval_s,
        "need_type": req["need_type"],
        "urgency": req["urgency"],
        "authority_state": authority,
        "external_send_authorized": False,
        "spend_authorized": False,
        "promise_of_aid_authorized": False,
        "reasons": sorted(set(reasons)),
        "recommendations": recommendations,
        "actions": sorted(actions, key=lambda a: a["action_id"]),
        "model_advisory": None,
    }
    return plan_core


def compile_plan_historical(request: Any, catalog: Any, evaluated_at: datetime) -> dict[str, Any]:
    if evaluated_at.tzinfo is None:
        raise PolicyError("historical evaluated_at must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(timezone.utc).replace(microsecond=0)
    req = _validate_request(request, evaluated_at)
    cat = _validate_catalog(catalog, evaluated_at)
    plan = _compile(req, cat, evaluated_at)
    input_bundle = {"request": req, "catalog": cat}
    plan_digest = sha256_hex(plan)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "policy_version": POLICY_VERSION,
        "case_id": req["case_id"],
        "evaluated_at": plan["evaluated_at"],
        "input_sha256": sha256_hex(input_bundle),
        "plan_sha256": plan_digest,
    }
    receipt["receipt_sha256"] = sha256_hex(receipt)
    return {"request": req, "catalog": cat, "plan": plan, "receipt": receipt}


def compile_plan(request: Any, catalog: Any) -> dict[str, Any]:
    """Compile against trusted process time. Current-mode callers cannot supply the clock."""
    return compile_plan_historical(request, catalog, datetime.now(timezone.utc))


def attach_model_advisory(package: dict[str, Any], advisory: dict[str, Any]) -> dict[str, Any]:
    """Attach non-authoritative model output without changing the deterministic receipt.

    The advisory is deliberately outside the receipt-bound plan so model prose cannot remint authority.
    """
    out = deepcopy(package)
    if not isinstance(advisory, dict) or set(advisory) != {"provider", "status", "text", "tool_calls"}:
        raise PolicyError("advisory shape invalid")
    if advisory["provider"] not in {"GLOO", "SIMULATOR"}:
        raise PolicyError("advisory provider invalid")
    if advisory["status"] not in {"LIVE", "SIMULATED", "UNAVAILABLE", "ERROR"}:
        raise PolicyError("advisory status invalid")
    if not isinstance(advisory["text"], str) or len(advisory["text"]) > 2000:
        raise PolicyError("advisory text invalid")
    if not isinstance(advisory["tool_calls"], list) or len(advisory["tool_calls"]) > 8:
        raise PolicyError("advisory tool_calls invalid")
    for call in advisory["tool_calls"]:
        if not isinstance(call, dict) or set(call) != {"name", "arguments"}:
            raise PolicyError("tool call shape invalid")
        if call["name"] not in {"explain_match", "draft_followup_question"}:
            raise PolicyError("unsupported model tool call")
        if not isinstance(call["arguments"], dict):
            raise PolicyError("tool arguments invalid")
    out["advisory"] = deepcopy(advisory)
    return out


def verify_receipt(package: Any) -> dict[str, Any]:
    try:
        package = _require_object(package, "package")
        if not {"request", "catalog", "plan", "receipt"}.issubset(package):
            return {"ok": False, "reason": "PACKAGE_FIELDS_MISSING"}
        plan = package["plan"]
        receipt = package["receipt"]
        evaluated = _parse_ts(receipt.get("evaluated_at", ""), "receipt.evaluated_at")
        replay = compile_plan_historical(package["request"], package["catalog"], evaluated)
        if replay["plan"] != plan:
            return {"ok": False, "reason": "PLAN_SEMANTIC_MISMATCH"}
        if replay["receipt"] != receipt:
            return {"ok": False, "reason": "RECEIPT_MISMATCH"}
        return {"ok": True, "reason": "VERIFIED", "receipt_sha256": receipt["receipt_sha256"]}
    except (PolicyError, CanonicalError, KeyError, TypeError) as exc:
        return {"ok": False, "reason": f"INVALID:{exc}"}
