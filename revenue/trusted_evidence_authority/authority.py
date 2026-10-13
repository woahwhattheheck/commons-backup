from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .strict_json import StrictJsonError, canonical_json, loads_strict, validate_json_value

HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
UTC = timezone.utc


class AuthorityError(ValueError):
    pass


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise AuthorityError(f"{field} must be a UTC timestamp string")
    if not value.endswith("Z"):
        raise AuthorityError(f"{field} must end in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise AuthorityError(f"invalid {field}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise AuthorityError(f"{field} must be UTC")
    return dt.astimezone(UTC)


def _utc_z(dt: datetime) -> str:
    dt = dt.astimezone(UTC)
    if dt.microsecond:
        return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise AuthorityError(f"invalid {field}")
    return value


def _require_hex64(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise AuthorityError(f"invalid {field}")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], optional: set[str] = set()) -> None:
    actual = set(value)
    if missing := required - actual:
        raise AuthorityError(f"missing keys: {','.join(sorted(missing))}")
    if extra := actual - required - optional:
        raise AuthorityError(f"unknown keys: {','.join(sorted(extra))}")


@dataclass(frozen=True)
class TrustedRegistry:
    raw: dict[str, Any]
    canonical_sha256: str
    pin_sha256: str

    @property
    def registry_id(self) -> str:
        return self.raw["registry_id"]

    @property
    def sources(self) -> dict[str, dict[str, Any]]:
        return {row["source_id"]: row for row in self.raw["sources"]}

    @property
    def required_source_ids(self) -> set[str]:
        return {row["source_id"] for row in self.raw["sources"] if row["required"]}


def validate_registry(value: Any) -> dict[str, Any]:
    validate_json_value(value)
    if not isinstance(value, dict):
        raise AuthorityError("registry must be an object")
    _exact_keys(value, {"schema", "registry_id", "issued_at", "sources"})
    if value["schema"] != "trusted-evidence-authority-registry/v1":
        raise AuthorityError("unsupported registry schema")
    _require_id(value["registry_id"], "registry_id")
    _parse_utc(value["issued_at"], "issued_at")
    rows = value["sources"]
    if not isinstance(rows, list) or not rows:
        raise AuthorityError("sources must be a non-empty list")
    seen: set[str] = set()
    seen_scope: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise AuthorityError("source commitment must be an object")
        _exact_keys(
            row,
            {
                "source_id", "provider", "scope", "resource", "generation",
                "content_sha256", "captured_at", "max_age_seconds", "required"
            },
        )
        sid = _require_id(row["source_id"], "source_id")
        provider = _require_id(row["provider"], "provider")
        scope = _require_id(row["scope"], "scope")
        _require_id(row["resource"], "resource")
        if sid in seen:
            raise AuthorityError(f"duplicate source_id: {sid}")
        seen.add(sid)
        if (provider, scope) in seen_scope:
            raise AuthorityError(f"ambiguous provider/scope: {provider}/{scope}")
        seen_scope.add((provider, scope))
        if not isinstance(row["generation"], int) or isinstance(row["generation"], bool) or row["generation"] < 1:
            raise AuthorityError("generation must be a positive integer")
        _require_hex64(row["content_sha256"], "content_sha256")
        _parse_utc(row["captured_at"], "captured_at")
        if not isinstance(row["max_age_seconds"], int) or isinstance(row["max_age_seconds"], bool) or row["max_age_seconds"] < 0:
            raise AuthorityError("max_age_seconds must be a non-negative integer")
        if not isinstance(row["required"], bool):
            raise AuthorityError("required must be boolean")
    return value


def load_trusted_registry(path: str | Path, *, expected_file_sha256: str) -> TrustedRegistry:
    expected_file_sha256 = _require_hex64(expected_file_sha256, "expected_file_sha256")
    data = Path(path).read_bytes()
    observed = sha256_bytes(data)
    if observed != expected_file_sha256:
        raise AuthorityError("trusted registry file digest does not match independently pinned digest")
    try:
        raw = loads_strict(data.decode("utf-8"))
    except (UnicodeDecodeError, StrictJsonError) as exc:
        raise AuthorityError(f"invalid trusted registry: {exc}") from exc
    raw = validate_registry(raw)
    return TrustedRegistry(raw=raw, canonical_sha256=sha256_text(canonical_json(raw)), pin_sha256=observed)


def _snapshot_trusted_registry(registry: TrustedRegistry) -> TrustedRegistry:
    """Verify the loaded commitment and detach state used by this verification."""
    try:
        canonical = canonical_json(registry.raw)
        observed = sha256_text(canonical)
        raw = validate_registry(loads_strict(canonical))
    except (ValueError, TypeError, RecursionError) as exc:
        raise AuthorityError("trusted registry state is invalid") from exc
    if observed != registry.canonical_sha256:
        raise AuthorityError("trusted registry changed after loading")
    return TrustedRegistry(raw=raw, canonical_sha256=registry.canonical_sha256, pin_sha256=registry.pin_sha256)


def registry_from_value_for_tests(value: dict[str, Any]) -> TrustedRegistry:
    """Test/library helper. Production CLI intentionally does not expose this as a trust upgrade."""
    raw = validate_registry(value)
    canonical = canonical_json(raw)
    return TrustedRegistry(raw=raw, canonical_sha256=sha256_text(canonical), pin_sha256=sha256_text(canonical))


def validate_packet(value: Any) -> dict[str, Any]:
    validate_json_value(value)
    if not isinstance(value, dict):
        raise AuthorityError("packet must be an object")
    _exact_keys(value, {"schema", "registry_id", "subject_id", "decision_id", "payload", "payload_sha256", "sources"})
    if value["schema"] != "trusted-evidence-authority-packet/v1":
        raise AuthorityError("unsupported packet schema")
    _require_id(value["registry_id"], "registry_id")
    _require_id(value["subject_id"], "subject_id")
    _require_id(value["decision_id"], "decision_id")
    validate_json_value(value["payload"], path="$.payload")
    expected_payload_sha = sha256_text(canonical_json(value["payload"]))
    if _require_hex64(value["payload_sha256"], "payload_sha256") != expected_payload_sha:
        raise AuthorityError("payload_sha256 mismatch")
    rows = value["sources"]
    if not isinstance(rows, list):
        raise AuthorityError("sources must be a list")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise AuthorityError("packet source must be an object")
        _exact_keys(row, {"source_id", "provider", "scope", "resource", "generation", "content_sha256", "captured_at"})
        sid = _require_id(row["source_id"], "source_id")
        if sid in seen:
            raise AuthorityError(f"duplicate packet source_id: {sid}")
        seen.add(sid)
        _require_id(row["provider"], "provider")
        _require_id(row["scope"], "scope")
        _require_id(row["resource"], "resource")
        if not isinstance(row["generation"], int) or isinstance(row["generation"], bool) or row["generation"] < 1:
            raise AuthorityError("generation must be a positive integer")
        _require_hex64(row["content_sha256"], "content_sha256")
        _parse_utc(row["captured_at"], "captured_at")
    return value


def packet_from_text(text: str) -> dict[str, Any]:
    try:
        return validate_packet(loads_strict(text))
    except StrictJsonError as exc:
        raise AuthorityError(str(exc)) from exc


def make_packet(*, registry_id: str, subject_id: str, decision_id: str, payload: Any, sources: Iterable[dict[str, Any]]) -> dict[str, Any]:
    validate_json_value(payload, path="$.payload")
    packet = {
        "schema": "trusted-evidence-authority-packet/v1",
        "registry_id": registry_id,
        "subject_id": subject_id,
        "decision_id": decision_id,
        "payload": payload,
        "payload_sha256": sha256_text(canonical_json(payload)),
        "sources": list(sources),
    }
    return validate_packet(packet)


def _source_mismatches(packet: dict[str, Any], registry: TrustedRegistry, at: datetime, *, enforce_freshness: bool) -> list[str]:
    reasons: list[str] = []
    packet_rows = {row["source_id"]: row for row in packet["sources"]}
    trusted_rows = registry.sources
    if set(packet_rows) != set(trusted_rows):
        missing = sorted(set(trusted_rows) - set(packet_rows))
        extra = sorted(set(packet_rows) - set(trusted_rows))
        if missing:
            reasons.append("MISSING_SOURCE:" + ",".join(missing))
        if extra:
            reasons.append("UNKNOWN_SOURCE:" + ",".join(extra))
    for source_id in sorted(set(packet_rows) & set(trusted_rows)):
        actual = packet_rows[source_id]
        expected = trusted_rows[source_id]
        for field in ("provider", "scope", "resource", "generation", "content_sha256", "captured_at"):
            if actual[field] != expected[field]:
                reasons.append(f"SOURCE_MISMATCH:{source_id}:{field}")
        captured = _parse_utc(expected["captured_at"], "captured_at")
        if at < captured:
            reasons.append(f"SOURCE_FROM_FUTURE:{source_id}")
        if enforce_freshness:
            age = (at - captured).total_seconds()
            if age > expected["max_age_seconds"]:
                reasons.append(f"STALE_SOURCE:{source_id}")
    required_missing = sorted(registry.required_source_ids - set(packet_rows))
    for source_id in required_missing:
        marker = f"MISSING_REQUIRED_SOURCE:{source_id}"
        if marker not in reasons:
            reasons.append(marker)
    return reasons


def _receipt(packet: dict[str, Any], registry: TrustedRegistry, *, level: str, verified_at: datetime, reasons: list[str]) -> dict[str, Any]:
    body = {
        "schema": "trusted-evidence-authority-receipt/v1",
        "evidence_level": level,
        "current_source_authority": level == "CURRENT_SOURCE_AUTHORITY" and not reasons,
        "registry_id": registry.registry_id,
        "registry_canonical_sha256": registry.canonical_sha256,
        "registry_pin_sha256": registry.pin_sha256,
        "subject_id": packet["subject_id"],
        "decision_id": packet["decision_id"],
        "payload_sha256": packet["payload_sha256"],
        "packet_sha256": sha256_text(canonical_json(packet)),
        "verified_at": _utc_z(verified_at),
        "reasons": sorted(set(reasons)),
        "authority_ceiling": "source provenance/currentness only; no decision correctness, provider action, payment, legal/compliance, or external authorization",
    }
    return {**body, "receipt_sha256": sha256_text(canonical_json(body))}


def verify_current(packet: dict[str, Any], registry: TrustedRegistry, *, now: datetime | None = None) -> dict[str, Any]:
    packet = validate_packet(packet)
    registry = _snapshot_trusted_registry(registry)
    if packet["registry_id"] != registry.registry_id:
        raise AuthorityError("packet registry_id mismatch")
    now = datetime.now(UTC) if now is None else now.astimezone(UTC)
    reasons = _source_mismatches(packet, registry, now, enforce_freshness=True)
    level = "CURRENT_SOURCE_AUTHORITY" if not reasons else "HOLD"
    return _receipt(packet, registry, level=level, verified_at=now, reasons=reasons)


def verify_historical(packet: dict[str, Any], registry: TrustedRegistry, *, as_of: datetime) -> dict[str, Any]:
    """Forensic replay only. Never upgrades historical evidence to current authority."""
    packet = validate_packet(packet)
    registry = _snapshot_trusted_registry(registry)
    if packet["registry_id"] != registry.registry_id:
        raise AuthorityError("packet registry_id mismatch")
    as_of = as_of.astimezone(UTC)
    reasons = _source_mismatches(packet, registry, as_of, enforce_freshness=False)
    return _receipt(packet, registry, level="HISTORICAL_INTEGRITY", verified_at=as_of, reasons=reasons)


def verify_receipt(receipt: dict[str, Any]) -> bool:
    try:
        validate_json_value(receipt)
        if not isinstance(receipt, dict):
            return False
        digest = receipt.get("receipt_sha256")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            return False
        body = dict(receipt)
        body.pop("receipt_sha256", None)
        return sha256_text(canonical_json(body)) == digest
    except (AuthorityError, StrictJsonError, ValueError, TypeError):
        return False
