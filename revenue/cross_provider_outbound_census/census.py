"""Cross-provider outbound collision-history gate with a host-owned authority boundary.

Untrusted claimant input contains only the canonical outbound lease seam and the
current send intent. It cannot provide the clock, fallback/alias registry, or
provider-history snapshots. Those facts are obtained from a host-owned
``TrustedCensusAuthority`` implementation at evaluation time.

This module is not send authority. Its strongest result is
``CLEAR_FOR_DOWNSTREAM_GATES`` and every packet keeps external send, lease, and
provider mutation authority false.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from revenue.outbound_connector_lease.key import (
    LeaseKeyError,
    SUPPORTED_REPLY_PROVIDERS,
    compile_document as compile_lease_document,
)

REQUEST_SCHEMA = "commons-cross-provider-outbound-census/request-v2"
REGISTRY_SCHEMA = "commons-cross-provider-outbound-census/registry-snapshot-v1"
PROVIDER_SCHEMA = "commons-cross-provider-outbound-census/provider-snapshot-v1"
PACKET_SCHEMA = "commons-cross-provider-outbound-census/packet-v2"
MAX_SAFE_INTEGER = (1 << 53) - 1
MAX_ROWS = 100_000
MAX_DEPTH = 40
MAX_INTENT_AGE_SECONDS = 300
MAX_REGISTRY_AGE_SECONDS = 300
MAX_PROVIDER_AGE_SECONDS = 300
_SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9._:/#@+\-]{1,190}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REGISTRY_STATES = frozenset({"COMPLETE", "UNAVAILABLE", "AMBIGUOUS"})
_PROVIDER_STATES = frozenset({"COMPLETE", "THROTTLED", "UNAVAILABLE", "AMBIGUOUS"})
_EVENTS = frozenset({
    "PROVIDER_SENT", "HUMAN_REPLY", "AUTO_REPLY", "HARD_BOUNCE", "SOFT_BOUNCE",
    "PROVIDER_REJECTED", "UNSUBSCRIBE", "DNR", "AMBIGUOUS_EFFECT",
})


class CensusError(ValueError):
    """Malformed candidate or malformed authority material."""


class AuthorityUnavailable(RuntimeError):
    """Trusted host could not obtain one required authority fact."""


class TrustedCensusAuthority(ABC):
    """Host-only authority interface chosen outside claimant-controlled data."""

    @abstractmethod
    def current_utc(self) -> str:
        """Return host current time as canonical whole-second UTC."""

    @abstractmethod
    def alias_registry(self, lease_key: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a fresh retained alias-registry snapshot for this seam."""

    @abstractmethod
    def provider_census(
        self,
        lease_key: Mapping[str, Any],
        provider: str,
        registered_routes: Sequence[str],
        registry_generation_id: str,
        intent: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Return fresh provider history, or None if no snapshot exists."""


def _walk(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise CensusError("JSON graph exceeds maximum nesting depth")
    t = type(value)
    if value is None or t in (str, bool):
        return
    if t is int:
        if abs(value) > MAX_SAFE_INTEGER:
            raise CensusError("integer exceeds safe interoperability range")
        return
    if t is float:
        if not math.isfinite(value):
            raise CensusError("non-finite number forbidden")
        return
    if t is list:
        if len(value) > MAX_ROWS:
            raise CensusError("array exceeds row limit")
        for item in value:
            _walk(item, depth + 1)
        return
    if t is dict:
        if len(value) > MAX_ROWS:
            raise CensusError("object exceeds member limit")
        for key, item in value.items():
            if type(key) is not str:
                raise CensusError("object key must be built-in string")
            _walk(item, depth + 1)
        return
    raise CensusError("value must be an inert built-in JSON graph")


def _canonical_bytes(value: Any) -> bytes:
    _walk(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise CensusError("value is not canonical JSON") from exc


def _snapshot(value: Any) -> Any:
    return json.loads(_canonical_bytes(value).decode("ascii"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact(value: Any, fields: set[str], where: str) -> None:
    if type(value) is not dict:
        raise CensusError(f"{where} must be an object")
    actual = set(value)
    if actual != fields:
        raise CensusError(
            f"{where} fields differ: missing={sorted(fields-actual)} extra={sorted(actual-fields)}"
        )


def _scope(value: Any, where: str) -> str:
    if type(value) is not str or _SCOPE_RE.fullmatch(value) is None:
        raise CensusError(f"{where} must be a lowercase opaque scope id")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise CensusError(f"{where} must be lowercase sha256")
    return value


def _provider(value: Any, where: str) -> str:
    if type(value) is not str or value not in SUPPORTED_REPLY_PROVIDERS:
        raise CensusError(f"{where} unsupported provider")
    return value


def _utc(value: Any, where: str) -> datetime:
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        raise CensusError(f"{where} must be canonical whole-second UTC ending Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CensusError(f"{where} is not a real UTC instant") from exc
    if parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise CensusError(f"{where} must be canonical whole-second UTC")
    return parsed


def _epoch(value: datetime) -> int:
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86400 + delta.seconds


def _utc_from_epoch(value: int) -> str:
    return datetime.fromtimestamp(value, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_request(raw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    value = _snapshot(raw)
    _exact(value, {"schema", "lease_input", "intent"}, "request")
    if value["schema"] != REQUEST_SCHEMA:
        raise CensusError("unsupported request schema")
    try:
        lease_key = compile_lease_document(value["lease_input"])
    except LeaseKeyError as exc:
        raise CensusError(f"invalid canonical outbound lease input: {exc}") from exc
    lease_input = {
        "schema": lease_key["schema"],
        "buyer_scope": lease_key["buyer_scope"],
        "opportunity": lease_key["opportunity"],
    }
    intent = value["intent"]
    _exact(intent, {"provider", "route_sha256", "claimant_scope", "claim_scope", "requested_at"}, "intent")
    normalized_intent = {
        "provider": _provider(intent["provider"], "intent.provider"),
        "route_sha256": _sha(intent["route_sha256"], "intent.route_sha256"),
        "claimant_scope": _scope(intent["claimant_scope"], "intent.claimant_scope"),
        "claim_scope": _scope(intent["claim_scope"], "intent.claim_scope"),
        "requested_at": intent["requested_at"],
    }
    _utc(normalized_intent["requested_at"], "intent.requested_at")
    return {
        "schema": REQUEST_SCHEMA,
        "lease_input": lease_input,
        "intent": normalized_intent,
    }, lease_key


def _normalize_alias_registry(raw: Any, lease_key: Mapping[str, Any]) -> dict[str, Any]:
    value = _snapshot(raw)
    _exact(value, {
        "schema", "lease_seam_sha256", "generation_id", "status", "observed_at",
        "source_receipt_sha256", "aliases",
    }, "authority registry")
    if value["schema"] != REGISTRY_SCHEMA:
        raise CensusError("unsupported authority registry schema")
    if _sha(value["lease_seam_sha256"], "registry.lease_seam_sha256") != lease_key["seam_sha256"]:
        raise CensusError("authority registry bound to a different lease seam")
    generation = _scope(value["generation_id"], "registry.generation_id")
    status = value["status"]
    if type(status) is not str or status not in _REGISTRY_STATES:
        raise CensusError("registry.status invalid")
    _utc(value["observed_at"], "registry.observed_at")
    receipt = _sha(value["source_receipt_sha256"], "registry.source_receipt_sha256")
    aliases_raw = value["aliases"]
    if type(aliases_raw) is not list:
        raise CensusError("registry.aliases must be an array")
    aliases: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for idx, row in enumerate(aliases_raw):
        where = f"registry.aliases[{idx}]"
        _exact(row, {"provider", "route_sha256"}, where)
        alias = {
            "provider": _provider(row["provider"], f"{where}.provider"),
            "route_sha256": _sha(row["route_sha256"], f"{where}.route_sha256"),
        }
        key = (alias["provider"], alias["route_sha256"])
        if key in seen:
            raise CensusError("duplicate retained provider route alias")
        seen.add(key)
        aliases.append(alias)
    aliases.sort(key=lambda row: (row["provider"], row["route_sha256"]))
    if status == "COMPLETE" and not aliases:
        raise CensusError("complete retained registry cannot be empty")
    return {
        "schema": REGISTRY_SCHEMA,
        "lease_seam_sha256": lease_key["seam_sha256"],
        "generation_id": generation,
        "status": status,
        "observed_at": value["observed_at"],
        "source_receipt_sha256": receipt,
        "aliases": aliases,
    }


def _normalize_provider_snapshot(raw: Any, *, lease_key: Mapping[str, Any], provider: str,
                                 registry_generation_id: str,
                                 registered_routes: set[str]) -> dict[str, Any]:
    value = _snapshot(raw)
    _exact(value, {
        "schema", "lease_seam_sha256", "registry_generation_id", "generation_id",
        "provider", "status", "observed_at", "source_receipt_sha256", "covered_routes", "events",
    }, f"authority provider snapshot:{provider}")
    if value["schema"] != PROVIDER_SCHEMA:
        raise CensusError("unsupported provider snapshot schema")
    if _sha(value["lease_seam_sha256"], "provider_snapshot.lease_seam_sha256") != lease_key["seam_sha256"]:
        raise CensusError("provider snapshot bound to a different lease seam")
    if _scope(value["registry_generation_id"], "provider_snapshot.registry_generation_id") != registry_generation_id:
        raise CensusError("provider snapshot bound to a different registry generation")
    generation = _scope(value["generation_id"], "provider_snapshot.generation_id")
    actual_provider = _provider(value["provider"], "provider_snapshot.provider")
    if actual_provider != provider:
        raise CensusError("provider snapshot identity mismatch")
    status = value["status"]
    if type(status) is not str or status not in _PROVIDER_STATES:
        raise CensusError("provider snapshot status invalid")
    observed = value["observed_at"]
    _utc(observed, "provider_snapshot.observed_at")
    source_receipt = _sha(value["source_receipt_sha256"], "provider_snapshot.source_receipt_sha256")
    covered_raw = value["covered_routes"]
    if type(covered_raw) is not list:
        raise CensusError("provider_snapshot.covered_routes must be an array")
    covered = [_sha(route, "provider_snapshot.covered_routes[]") for route in covered_raw]
    if len(set(covered)) != len(covered):
        raise CensusError("duplicate covered route")
    covered.sort()
    events_raw = value["events"]
    if type(events_raw) is not list:
        raise CensusError("provider_snapshot.events must be an array")
    events: list[dict[str, str]] = []
    evidence_ids: set[str] = set()
    observed_dt = _utc(observed, "provider_snapshot.observed_at")
    for idx, item in enumerate(events_raw):
        where = f"provider_snapshot.events[{idx}]"
        _exact(item, {"route_sha256", "event", "event_at", "evidence_sha256"}, where)
        route = _sha(item["route_sha256"], f"{where}.route_sha256")
        if route not in registered_routes:
            raise CensusError("provider event route is not in retained registry")
        kind = item["event"]
        if type(kind) is not str or kind not in _EVENTS:
            raise CensusError(f"{where}.event invalid")
        event_at = item["event_at"]
        if _utc(event_at, f"{where}.event_at") > observed_dt:
            raise CensusError("provider event cannot occur after snapshot observation")
        evidence = _sha(item["evidence_sha256"], f"{where}.evidence_sha256")
        if evidence in evidence_ids:
            raise CensusError("duplicate provider evidence event")
        evidence_ids.add(evidence)
        events.append({
            "route_sha256": route, "event": kind, "event_at": event_at,
            "evidence_sha256": evidence,
        })
    events.sort(key=lambda row: (row["event_at"], row["route_sha256"], row["event"], row["evidence_sha256"]))
    return {
        "schema": PROVIDER_SCHEMA,
        "lease_seam_sha256": lease_key["seam_sha256"],
        "registry_generation_id": registry_generation_id,
        "generation_id": generation,
        "provider": provider,
        "status": status,
        "observed_at": observed,
        "source_receipt_sha256": source_receipt,
        "covered_routes": covered,
        "events": events,
    }


def _packet_receipt(packet_without_receipt: Mapping[str, Any]) -> str:
    return _digest(packet_without_receipt)


def compile_census(raw: Any, *, authority: TrustedCensusAuthority) -> dict[str, Any]:
    """Evaluate one claimant request against host-owned registry/history authority."""
    if not isinstance(authority, TrustedCensusAuthority):
        raise CensusError("authority must be a TrustedCensusAuthority chosen by the host")
    request, lease_key = _normalize_request(raw)
    now_text = authority.current_utc()
    now = _utc(now_text, "authority.current_utc")
    now_epoch = _epoch(now)
    requested = _utc(request["intent"]["requested_at"], "intent.requested_at")
    requested_epoch = _epoch(requested)
    reasons: list[str] = []
    if requested > now:
        reasons.append("INTENT_REQUESTED_IN_FUTURE")
    elif now_epoch - requested_epoch > MAX_INTENT_AGE_SECONDS:
        reasons.append("INTENT_STALE")

    try:
        registry_raw = authority.alias_registry(_snapshot(lease_key))
    except AuthorityUnavailable:
        registry_raw = {
            "schema": REGISTRY_SCHEMA,
            "lease_seam_sha256": lease_key["seam_sha256"],
            "generation_id": "authority-unavailable",
            "status": "UNAVAILABLE",
            "observed_at": now_text,
            "source_receipt_sha256": "0" * 64,
            "aliases": [],
        }
    registry = _normalize_alias_registry(registry_raw, lease_key)
    registry_observed = _utc(registry["observed_at"], "registry.observed_at")
    registry_epoch = _epoch(registry_observed)
    if registry["status"] != "COMPLETE":
        reasons.append(f"ALIAS_REGISTRY_{registry['status']}")
    if registry_observed > now:
        reasons.append("ALIAS_REGISTRY_FUTURE")
    elif registry_observed < requested:
        reasons.append("ALIAS_REGISTRY_BEFORE_INTENT")
    elif now_epoch - registry_epoch > MAX_REGISTRY_AGE_SECONDS:
        reasons.append("ALIAS_REGISTRY_STALE")

    aliases_by_provider: dict[str, set[str]] = {}
    alias_keys: set[tuple[str, str]] = set()
    for alias in registry["aliases"]:
        aliases_by_provider.setdefault(alias["provider"], set()).add(alias["route_sha256"])
        alias_keys.add((alias["provider"], alias["route_sha256"]))
    intent_key = (request["intent"]["provider"], request["intent"]["route_sha256"])
    if intent_key not in alias_keys:
        reasons.append("INTENT_ROUTE_NOT_IN_RETAINED_REGISTRY")

    clear_expiries = [requested_epoch + MAX_INTENT_AGE_SECONDS]
    if registry["status"] == "COMPLETE":
        clear_expiries.append(registry_epoch + MAX_REGISTRY_AGE_SECONDS)
    provider_rows: list[dict[str, Any]] = []
    all_events: list[tuple[str, dict[str, str]]] = []

    for provider in sorted(aliases_by_provider):
        routes = aliases_by_provider[provider]
        try:
            raw_snapshot = authority.provider_census(
                _snapshot(lease_key), provider, tuple(sorted(routes)),
                registry["generation_id"], _snapshot(request["intent"]),
            )
        except AuthorityUnavailable:
            raw_snapshot = None
        if raw_snapshot is None:
            reasons.append(f"PROVIDER_CENSUS_MISSING:{provider}")
            provider_rows.append({
                "provider": provider, "status": "MISSING", "generation_id": None,
                "observed_at": None, "source_receipt_sha256": None,
                "registered_routes": len(routes), "covered_routes": 0,
                "history_events": 0, "snapshot_sha256": None,
            })
            continue
        snap = _normalize_provider_snapshot(
            raw_snapshot, lease_key=lease_key, provider=provider,
            registry_generation_id=registry["generation_id"], registered_routes=routes,
        )
        for item in snap["events"]:
            all_events.append((provider, item))
        provider_rows.append({
            "provider": provider, "status": snap["status"],
            "generation_id": snap["generation_id"], "observed_at": snap["observed_at"],
            "source_receipt_sha256": snap["source_receipt_sha256"],
            "registered_routes": len(routes), "covered_routes": len(snap["covered_routes"]),
            "history_events": len(snap["events"]), "snapshot_sha256": _digest(snap),
        })
        if snap["status"] != "COMPLETE":
            reasons.append(f"PROVIDER_CENSUS_{snap['status']}:{provider}")
            continue
        observed = _utc(snap["observed_at"], f"provider.{provider}.observed_at")
        observed_epoch = _epoch(observed)
        clear_expiries.append(observed_epoch + MAX_PROVIDER_AGE_SECONDS)
        if observed > now:
            reasons.append(f"PROVIDER_CENSUS_FUTURE:{provider}")
        elif observed < requested:
            reasons.append(f"PROVIDER_CENSUS_BEFORE_INTENT:{provider}")
        elif observed < registry_observed:
            reasons.append(f"PROVIDER_CENSUS_BEFORE_REGISTRY:{provider}")
        elif now_epoch - observed_epoch > MAX_PROVIDER_AGE_SECONDS:
            reasons.append(f"PROVIDER_CENSUS_STALE:{provider}")
        missing = routes - set(snap["covered_routes"])
        extra = set(snap["covered_routes"]) - routes
        if missing:
            reasons.append(f"PROVIDER_ROUTE_COVERAGE_MISSING:{provider}")
        if extra:
            reasons.append(f"PROVIDER_ROUTE_COVERAGE_UNKNOWN:{provider}")

    kinds = {item["event"] for _, item in all_events}
    if kinds & {"UNSUBSCRIBE", "DNR"}:
        reasons.append("SUPPRESSION_HISTORY")
    if kinds & {"PROVIDER_SENT", "HUMAN_REPLY", "AUTO_REPLY"}:
        reasons.append("EXISTING_TOUCH_HISTORY")
    if kinds & {"HARD_BOUNCE", "SOFT_BOUNCE", "PROVIDER_REJECTED"}:
        reasons.append("ROUTE_REPAIR_HISTORY")
    if kinds & {"AMBIGUOUS_EFFECT"}:
        reasons.append("AMBIGUOUS_PROVIDER_HISTORY")

    evidence = [{
        "provider": provider, "route_sha256": item["route_sha256"],
        "event": item["event"], "event_at": item["event_at"],
        "evidence_sha256": item["evidence_sha256"],
    } for provider, item in all_events]
    evidence.sort(key=lambda row: (
        row["event_at"], row["provider"], row["route_sha256"], row["event"], row["evidence_sha256"]
    ))
    reasons = sorted(set(reasons))
    result = "HOLD" if reasons else "CLEAR_FOR_DOWNSTREAM_GATES"
    clear_until = None if reasons else _utc_from_epoch(min(clear_expiries))
    body = {
        "schema": PACKET_SCHEMA,
        "request_sha256": _digest(request),
        "lease_seam_sha256": lease_key["seam_sha256"],
        "downstream_lease_branch": lease_key["branch"],
        "result": result,
        "reasons": reasons,
        "evaluated_at": now_text,
        "clear_until": clear_until,
        "authority": {
            "registry_generation_id": registry["generation_id"],
            "registry_status": registry["status"],
            "registry_observed_at": registry["observed_at"],
            "registry_source_receipt_sha256": registry["source_receipt_sha256"],
            "registry_snapshot_sha256": _digest(registry),
            "providers": provider_rows,
        },
        "history_evidence": evidence,
        "external_send_authorized": False,
        "lease_authorized": False,
        "provider_mutation_authorized": False,
    }
    return {**body, "packet_sha256": _packet_receipt(body)}


def verify_census(raw: Any, packet: Any, *, authority: TrustedCensusAuthority) -> None:
    """Fail closed unless a packet still matches fresh host authority."""
    if type(packet) is not dict:
        raise CensusError("packet must be an object")
    packet_copy = _snapshot(packet)
    if set(packet_copy) != {
        "schema", "request_sha256", "lease_seam_sha256", "downstream_lease_branch",
        "result", "reasons", "evaluated_at", "clear_until", "authority",
        "history_evidence", "external_send_authorized", "lease_authorized",
        "provider_mutation_authorized", "packet_sha256",
    }:
        raise CensusError("packet fields differ")
    receipt = packet_copy.pop("packet_sha256")
    if _sha(receipt, "packet.packet_sha256") != _packet_receipt(packet_copy):
        raise CensusError("packet receipt mismatch")
    if packet_copy["schema"] != PACKET_SCHEMA:
        raise CensusError("unsupported packet schema")
    if (packet_copy["external_send_authorized"] is not False or
            packet_copy["lease_authorized"] is not False or
            packet_copy["provider_mutation_authorized"] is not False):
        raise CensusError("packet illegally claims mutation authority")

    request, lease_key = _normalize_request(raw)
    if packet_copy["request_sha256"] != _digest(request):
        raise CensusError("request drift")
    if packet_copy["lease_seam_sha256"] != lease_key["seam_sha256"]:
        raise CensusError("lease seam drift")

    fresh = compile_census(request, authority=authority)
    if fresh["result"] != packet_copy["result"]:
        raise CensusError("authority decision changed")
    fresh_auth = fresh["authority"]
    old_auth = packet_copy["authority"]
    if fresh_auth["registry_generation_id"] != old_auth["registry_generation_id"]:
        raise CensusError("retained alias registry generation changed")
    if fresh_auth["registry_snapshot_sha256"] != old_auth["registry_snapshot_sha256"]:
        raise CensusError("retained alias registry snapshot changed")
    fresh_providers = {(p["provider"], p["generation_id"], p["snapshot_sha256"])
                       for p in fresh_auth["providers"]}
    old_providers = {(p["provider"], p["generation_id"], p["snapshot_sha256"])
                     for p in old_auth["providers"]}
    if fresh_providers != old_providers:
        raise CensusError("provider census generation changed")
    if fresh["history_evidence"] != packet_copy["history_evidence"]:
        raise CensusError("provider history changed")
    if packet_copy["result"] == "CLEAR_FOR_DOWNSTREAM_GATES":
        clear_until = _utc(packet_copy["clear_until"], "packet.clear_until")
        current = _utc(authority.current_utc(), "authority.current_utc")
        if current > clear_until:
            raise CensusError("clear packet expired")


__all__ = [
    "AuthorityUnavailable", "CensusError", "TrustedCensusAuthority",
    "compile_census", "verify_census",
]
