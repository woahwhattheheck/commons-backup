"""Deterministic, source-grounded routing core for FlourishRelay.

This module never contacts an external provider and never authorizes an external
side effect.  Its strongest output is a local RECOMMEND packet grounded in the
resource snapshots supplied by the caller.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = "flourish-relay.v1"
MAX_TEXT = 240
ALLOWED_ACTIONS = {
    "RECOMMEND",
    "CONTACT",
    "SPEND",
    "COMMIT",
    "SCHEDULE",
    "SHARE_SENSITIVE",
}
EXTERNAL_ACTIONS = ALLOWED_ACTIONS - {"RECOMMEND"}


class Status(str, Enum):
    SUPPORTED = "SUPPORTED"
    OWNER_INPUT = "OWNER_INPUT"
    GAP = "GAP"
    STALE = "STALE"
    HOLD = "HOLD"


class ContractError(ValueError):
    """Input failed the public/offline contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_exact_keys(obj: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise ContractError(f"{where}: unknown fields: {', '.join(unknown)}")


def _text(value: Any, field: str, *, lower: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field}: expected string")
    if value != value.strip() or not value or len(value) > MAX_TEXT:
        raise ContractError(f"{field}: invalid bounded text")
    return value.lower() if lower else value


def _time(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ContractError(f"{field}: invalid ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ContractError(f"{field}: timezone required")
    return dt.astimezone(timezone.utc)


def _https_url(value: Any, field: str) -> str:
    raw = _text(value, field)
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ContractError(f"{field}: public https URL required")
    return raw


def _string_list(value: Any, field: str, *, lower: bool = False, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ContractError(f"{field}: expected list")
    items = tuple(_text(v, field, lower=lower) for v in value)
    if not allow_empty and not items:
        raise ContractError(f"{field}: list must not be empty")
    if len(items) != len(set(items)):
        raise ContractError(f"{field}: duplicates forbidden")
    return items


@dataclass(frozen=True)
class Request:
    request_id: str
    topic: str
    requested_at: datetime
    owner_fields: Mapping[str, Any]
    budget_cents: int | None
    consent_to_recommend: bool
    sensitive_context: bool
    desired_actions: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Request":
        if not isinstance(raw, Mapping):
            raise ContractError("request: expected object")
        allowed = {
            "request_id", "topic", "requested_at", "owner_fields", "budget_cents",
            "consent_to_recommend", "sensitive_context", "desired_actions",
        }
        _require_exact_keys(raw, allowed, "request")
        owner_fields = raw.get("owner_fields", {})
        if not isinstance(owner_fields, Mapping):
            raise ContractError("request.owner_fields: expected object")
        if len(owner_fields) > 20:
            raise ContractError("request.owner_fields: too many fields")
        normalized_owner_fields: dict[str, Any] = {}
        for key, value in owner_fields.items():
            normalized_key = _text(key, "request.owner_fields key", lower=True)
            if key != normalized_key:
                raise ContractError("request.owner_fields keys must already be lowercase")
            if value is None or isinstance(value, bool):
                normalized_value = value
            elif isinstance(value, int) and not isinstance(value, bool):
                if abs(value) > 10**15:
                    raise ContractError("request.owner_fields integer exceeds bound")
                normalized_value = value
            elif isinstance(value, str):
                normalized_value = _text(value, f"request.owner_fields.{normalized_key}")
            else:
                raise ContractError("request.owner_fields values must be bounded JSON scalars")
            normalized_owner_fields[normalized_key] = normalized_value
        budget = raw.get("budget_cents")
        if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int) or budget < 0):
            raise ContractError("request.budget_cents: expected non-negative integer or null")
        consent = raw.get("consent_to_recommend", False)
        sensitive = raw.get("sensitive_context", False)
        if not isinstance(consent, bool) or not isinstance(sensitive, bool):
            raise ContractError("request consent/sensitive flags must be booleans")
        actions = _string_list(raw.get("desired_actions", ["RECOMMEND"]), "request.desired_actions")
        if set(actions) - ALLOWED_ACTIONS:
            raise ContractError("request.desired_actions: unsupported action")
        return cls(
            request_id=_text(raw.get("request_id"), "request.request_id"),
            topic=_text(raw.get("topic"), "request.topic", lower=True),
            requested_at=_time(raw.get("requested_at"), "request.requested_at"),
            owner_fields=normalized_owner_fields,
            budget_cents=budget,
            consent_to_recommend=consent,
            sensitive_context=sensitive,
            desired_actions=actions,
        )


@dataclass(frozen=True)
class Resource:
    resource_id: str
    name: str
    source_url: str
    observed_at: datetime
    expires_at: datetime | None
    capacity: str
    topics: tuple[str, ...]
    requires_owner_fields: tuple[str, ...]
    min_budget_cents: int | None
    max_budget_cents: int | None

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Resource":
        if not isinstance(raw, Mapping):
            raise ContractError("resource: expected object")
        allowed = {
            "resource_id", "name", "source_url", "observed_at", "expires_at",
            "capacity", "topics", "requires_owner_fields", "min_budget_cents",
            "max_budget_cents",
        }
        _require_exact_keys(raw, allowed, "resource")
        capacity = _text(raw.get("capacity"), "resource.capacity").upper()
        if capacity not in {"AVAILABLE", "LIMITED", "UNKNOWN", "CLOSED"}:
            raise ContractError("resource.capacity: unsupported state")
        minimum = raw.get("min_budget_cents")
        maximum = raw.get("max_budget_cents")
        for label, value in (("min_budget_cents", minimum), ("max_budget_cents", maximum)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ContractError(f"resource.{label}: expected non-negative integer or null")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ContractError("resource: minimum budget exceeds maximum")
        expires = raw.get("expires_at")
        return cls(
            resource_id=_text(raw.get("resource_id"), "resource.resource_id"),
            name=_text(raw.get("name"), "resource.name"),
            source_url=_https_url(raw.get("source_url"), "resource.source_url"),
            observed_at=_time(raw.get("observed_at"), "resource.observed_at"),
            expires_at=_time(expires, "resource.expires_at") if expires is not None else None,
            capacity=capacity,
            topics=_string_list(raw.get("topics"), "resource.topics", lower=True),
            requires_owner_fields=_string_list(
                raw.get("requires_owner_fields", []),
                "resource.requires_owner_fields",
                lower=True,
                allow_empty=True,
            ),
            min_budget_cents=minimum,
            max_budget_cents=maximum,
        )

    def public_view(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "source_url": self.source_url,
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "capacity": self.capacity,
        }


def _request_receipt_view(req: Request) -> dict[str, Any]:
    # Values in owner_fields are intentionally committed by hash but never echoed.
    return {
        "request_id": req.request_id,
        "topic": req.topic,
        "requested_at": req.requested_at.isoformat().replace("+00:00", "Z"),
        "owner_field_names": sorted(req.owner_fields),
        "budget_present": req.budget_cents is not None,
        "consent_to_recommend": req.consent_to_recommend,
        "sensitive_context": req.sensitive_context,
        "desired_actions": list(req.desired_actions),
    }


def _resource_receipt_view(resource: Resource) -> dict[str, Any]:
    return {
        **resource.public_view(),
        "expires_at": resource.expires_at.isoformat().replace("+00:00", "Z") if resource.expires_at else None,
        "topics": list(resource.topics),
        "requires_owner_fields": list(resource.requires_owner_fields),
        "min_budget_cents": resource.min_budget_cents,
        "max_budget_cents": resource.max_budget_cents,
    }


def _is_stale(resource: Resource, requested_at: datetime, max_age_days: int) -> bool:
    if resource.observed_at > requested_at:
        return True
    age_seconds = (requested_at - resource.observed_at).total_seconds()
    if age_seconds > max_age_days * 86400:
        return True
    if resource.expires_at is not None and requested_at > resource.expires_at:
        return True
    return False


def route(raw_request: Mapping[str, Any], raw_resources: Sequence[Mapping[str, Any]], *, max_age_days: int = 45) -> dict[str, Any]:
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or not (1 <= max_age_days <= 365):
        raise ContractError("max_age_days must be integer in [1,365]")
    req = Request.parse(raw_request)
    if not isinstance(raw_resources, Sequence) or isinstance(raw_resources, (str, bytes)):
        raise ContractError("resources: expected list")
    resources = [Resource.parse(x) for x in raw_resources]
    ids = [r.resource_id for r in resources]
    if len(ids) != len(set(ids)):
        raise ContractError("resources: duplicate resource_id")
    resources.sort(key=lambda r: r.resource_id)

    status: Status
    reasons: list[str] = []
    recommendations: list[dict[str, Any]] = []
    missing_fields: set[str] = set()

    requested_external = sorted(set(req.desired_actions) & EXTERNAL_ACTIONS)
    if not req.consent_to_recommend:
        status = Status.HOLD
        reasons.append("recommendation consent is absent")
    elif req.sensitive_context:
        status = Status.HOLD
        reasons.append("sensitive context requires human authority outside this carrier")
    elif requested_external:
        status = Status.HOLD
        reasons.append("requested external actions exceed local recommendation authority")
    else:
        topical = [r for r in resources if req.topic in r.topics]
        if not topical:
            status = Status.GAP
            reasons.append("no source snapshot covers the requested topic")
        else:
            current = [r for r in topical if not _is_stale(r, req.requested_at, max_age_days)]
            if not current:
                status = Status.STALE
                reasons.append("all topical source snapshots are stale, expired, or future-dated")
            else:
                viable: list[Resource] = []
                saw_unknown_capacity = False
                for resource in current:
                    if resource.capacity == "CLOSED":
                        continue
                    if resource.capacity == "UNKNOWN":
                        saw_unknown_capacity = True
                        continue
                    missing = set(resource.requires_owner_fields) - set(req.owner_fields)
                    if missing:
                        missing_fields.update(missing)
                        continue
                    if (resource.min_budget_cents is not None or resource.max_budget_cents is not None) and req.budget_cents is None:
                        missing_fields.add("budget_cents")
                        continue
                    if req.budget_cents is not None:
                        if resource.min_budget_cents is not None and req.budget_cents < resource.min_budget_cents:
                            continue
                        if resource.max_budget_cents is not None and req.budget_cents > resource.max_budget_cents:
                            continue
                    viable.append(resource)
                if viable:
                    status = Status.SUPPORTED
                    recommendations = [r.public_view() for r in viable]
                    reasons.append("one or more current owner-compatible resource snapshots support a local recommendation")
                elif missing_fields or saw_unknown_capacity:
                    status = Status.OWNER_INPUT
                    if missing_fields:
                        reasons.append("owner facts are required before a recommendation can be supported")
                    if saw_unknown_capacity:
                        reasons.append("current capacity must be confirmed by an authorized owner/provider")
                else:
                    status = Status.GAP
                    reasons.append("current topical resources fail capacity or budget gates")

    packet = {
        "schema": SCHEMA_VERSION,
        "request": _request_receipt_view(req),
        "status": status.value,
        "reasons": reasons,
        "recommendations": recommendations,
        "missing_owner_fields": sorted(missing_fields),
        "permitted_actions": ["RECOMMEND"] if status is Status.SUPPORTED else [],
        "denied_external_actions": sorted(EXTERNAL_ACTIONS),
        "authority": {
            "contact": False,
            "spend": False,
            "commit": False,
            "schedule": False,
            "share_sensitive": False,
        },
    }
    receipt = {
        "schema": SCHEMA_VERSION,
        "request_sha256": sha256_obj(dict(raw_request)),
        "resources_sha256": sha256_obj([_resource_receipt_view(r) for r in resources]),
        "packet_sha256": sha256_obj(packet),
        "max_age_days": max_age_days,
    }
    return {"packet": packet, "receipt": receipt}


def verify_replay(
    raw_request: Mapping[str, Any],
    raw_resources: Sequence[Mapping[str, Any]],
    expected: Mapping[str, Any],
) -> bool:
    if not isinstance(expected, Mapping):
        return False
    receipt = expected.get("receipt")
    if not isinstance(receipt, Mapping):
        return False
    max_age_days = receipt.get("max_age_days")
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int):
        return False
    try:
        actual = route(raw_request, raw_resources, max_age_days=max_age_days)
    except (ContractError, TypeError, ValueError):
        return False
    return _canonical(actual) == _canonical(expected)
