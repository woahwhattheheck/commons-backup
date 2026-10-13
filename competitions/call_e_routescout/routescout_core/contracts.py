from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


SCHEMA_VERSION = 1
OFFICIAL_API_ORIGIN = "https://api.heycall-e.com"
TERMINAL = {"completed", "failed", "canceled"}
CHANNEL_TYPES = {"email", "web_form", "phone", "portal", "other", "none"}
PERMISSION_STATES = {"invited", "permitted", "unclear", "declined"}
OUTCOMES = {"ROUTE_FOUND", "DO_NOT_CONTACT", "NO_ROUTE", "HUMAN_REQUIRED"}
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ALLOWED_CASE_KEYS = {
    "schema_version", "inquiry_id", "caller_org", "target_org", "phone_e164",
    "region", "locale", "source_url", "inquiry_kind", "inquiry_reference", "inquiry_topic",
    "requested_function", "operator_approved", "published_business_route",
}
_RESULT_FIELDS = {
    "organization_confirmed", "consented_to_continue", "routing_answered",
    "department_or_role", "channel_type", "channel_value", "channel_is_business",
    "permission_state", "do_not_contact", "verbatim_route", "notes",
}
_INQUIRY_KINDS = {"procurement_process", "vendor_registration", "existing_supplier_support", "partner_program_support"}
_SUPPORTED_REGIONS = {
    "US","SG","MY","IN","AE","AU","CA","GB","VN","DE","JP","FR","MX","BR","ID",
    "PH","KE","NL","PL","BD","NG","OM","TH","NA","CM","MZ","SA","FI",
}

class RouteScoutError(ValueError):
    pass

def _strict_json_load(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    def pairs(items):
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise RouteScoutError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise RouteScoutError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RouteScoutError("top-level JSON must be an object")
    return value

def _exact_keys(obj: Mapping[str, Any], expected: set[str], label: str) -> None:
    keys = set(obj)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing:
        raise RouteScoutError(f"{label}: missing keys: {', '.join(missing)}")
    if unknown:
        raise RouteScoutError(f"{label}: unknown keys: {', '.join(unknown)}")

def _text(value: Any, field: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RouteScoutError(f"{field}: must be string")
    if _CONTROL.search(value) or len(value) > limit or (not allow_empty and not value.strip()):
        raise RouteScoutError(f"{field}: invalid text")
    return value.strip()

def _https_url(value: Any, field: str) -> str:
    text = _text(value, field, 500)
    p = urlparse(text)
    if p.scheme != "https" or not p.netloc or p.username or p.password or p.query or p.fragment:
        raise RouteScoutError(f"{field}: must be a public https URL without credentials or fragment")
    return text

def validate_inquiry(inquiry: Mapping[str, Any]) -> dict[str, Any]:
    _exact_keys(inquiry, _ALLOWED_CASE_KEYS, "inquiry")
    if type(inquiry["schema_version"]) is not int or inquiry["schema_version"] != SCHEMA_VERSION:
        raise RouteScoutError("schema_version must be integer 1")
    if type(inquiry["operator_approved"]) is not bool or inquiry["operator_approved"] is not True:
        raise RouteScoutError("operator_approved must be true")
    if type(inquiry["published_business_route"]) is not bool or inquiry["published_business_route"] is not True:
        raise RouteScoutError("published_business_route must be true")
    out = {
        "schema_version": SCHEMA_VERSION,
        "inquiry_id": _text(inquiry["inquiry_id"], "inquiry_id", 80),
        "caller_org": _text(inquiry["caller_org"], "caller_org", 120),
        "target_org": _text(inquiry["target_org"], "target_org", 120),
        "phone_e164": _text(inquiry["phone_e164"], "phone_e164", 20),
        "region": _text(inquiry["region"], "region", 3),
        "locale": _text(inquiry["locale"], "locale", 16),
        "source_url": _https_url(inquiry["source_url"], "source_url"),
        "inquiry_kind": _text(inquiry["inquiry_kind"], "inquiry_kind", 40),
        "inquiry_reference": _text(inquiry["inquiry_reference"], "inquiry_reference", 120),
        "inquiry_topic": _text(inquiry["inquiry_topic"], "inquiry_topic", 240),
        "requested_function": _text(inquiry["requested_function"], "requested_function", 160),
        "operator_approved": True,
        "published_business_route": True,
    }
    if not _E164.fullmatch(out["phone_e164"]):
        raise RouteScoutError("phone_e164: must be E.164")
    if out["region"] not in _SUPPORTED_REGIONS:
        raise RouteScoutError("region: unsupported by this pinned RouteScout contract")
    if out["inquiry_kind"] not in _INQUIRY_KINDS:
        raise RouteScoutError("inquiry_kind: marketing, lead-generation, and unrecognized purposes are not supported")
    return out

def canonical_inquiry_bytes(inquiry: Mapping[str, Any]) -> bytes:
    i = validate_inquiry(inquiry)
    return (json.dumps(i, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")

def inquiry_digest(inquiry: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_inquiry_bytes(inquiry)).hexdigest()

def approval_token(inquiry: Mapping[str, Any]) -> str:
    # Deliberately not a secret/authenticator; it proves operator preview matches exact bytes.
    return "ROUTESCOUT-" + inquiry_digest(inquiry)[:20].upper()

def idempotency_key(inquiry: Mapping[str, Any]) -> str:
    return "routescout-" + inquiry_digest(inquiry)

def masked_phone(phone: str) -> str:
    return "*" * max(0, len(phone) - 4) + phone[-4:]

