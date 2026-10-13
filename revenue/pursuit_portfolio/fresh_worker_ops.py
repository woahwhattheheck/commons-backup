"""Compile/verify operations executed only inside the isolated worker."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any, Mapping

from .core import PortfolioError, load_json_bytes
from . import current
from . import host_kernel as host
from .floor import AuthorityFloor, require_current_authority
from .fresh_exec import WORKER_LIMIT
from .fresh_protocol import ARTIFACT_KEYS


def now_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def decode_artifacts(value: Any) -> dict[str, bytes]:
    if type(value) is not dict or set(value) != set(ARTIFACT_KEYS):
        raise PortfolioError("worker artifacts have wrong key set")
    decoded: dict[str, bytes] = {}
    for name in ARTIFACT_KEYS:
        encoded = value[name]
        if type(encoded) is not str:
            raise PortfolioError(f"worker artifact {name}: base64 text required")
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise PortfolioError(f"worker artifact {name}: invalid base64") from exc
        if len(raw) > WORKER_LIMIT:
            raise PortfolioError(f"worker artifact {name}: exceeds byte bound")
        decoded[name] = raw
    return decoded


def require_authority_chronology(
    authority: Mapping[str, Any],
    floor: AuthorityFloor,
    trusted_now: str,
) -> None:
    """Bind evidence -> authority -> retained-floor -> real-current chronology."""
    generated = current._dt(
        authority["generated_at"], "upstream authority.generated_at"
    )
    floor_updated = current._dt(
        floor.updated_at, "authority floor.updated_at"
    )
    now = current._dt(trusted_now, "trusted_now")
    if generated > floor_updated:
        raise PortfolioError(
            "authority chronology: generation postdates retained floor update"
        )
    if floor_updated > now:
        raise PortfolioError(
            "authority chronology: retained floor update is in the future"
        )
    for index, row in enumerate(authority["rows"]):
        evidence = current._dt(
            row["evidence_captured_at"],
            f"upstream authority.rows[{index}].evidence_captured_at",
        )
        if evidence > generated:
            raise PortfolioError(
                "authority chronology: evidence postdates authority generation"
            )


def compile_operation(request: dict[str, Any]) -> dict[str, Any]:
    if set(request) != {"action", "authority", "source"}:
        raise PortfolioError("worker compile request has wrong key set")
    source = request["source"]
    authority = request["authority"]
    if type(source) is not dict or type(authority) is not dict:
        raise PortfolioError("worker compile source and authority must be objects")

    trusted_now = now_utc()
    host_before = host.load_host_authority(trusted_now)
    key = host_before.key
    floor_before = host_before.floor
    normalized_authority, authority_bytes = current.canonical_authority(authority)
    require_current_authority(floor_before, authority_bytes)
    require_authority_chronology(normalized_authority, floor_before, trusted_now)
    authorized = current.compile_authorized_at(
        source, normalized_authority, key, trusted_now
    )
    if authorized.authority_bytes != authority_bytes:
        raise PortfolioError("worker authority canonicalization changed generation")
    host_seal = host.seal(authorized, key, floor_before)
    host_seal_bytes = current._canonical(host_seal)
    host_after = host.load_host_authority(trusted_now)
    host.same_host_authority(host_before, host_after)
    require_current_authority(host_after.floor, authorized.authority_bytes)
    require_authority_chronology(
        normalized_authority, host_after.floor, trusted_now
    )

    return {
        "ok": True,
        "artifacts": {
            "authority": b64(authorized.authority_bytes),
            "current_receipt": b64(authorized.current_receipt_bytes),
            "host_seal": b64(host_seal_bytes),
            "markdown": b64(authorized.compiled.markdown_bytes),
            "receipt": b64(authorized.compiled.receipt_bytes),
            "result": b64(authorized.compiled.result_bytes),
        },
        "values": {
            "authority": authorized.authority,
            "current_receipt": authorized.current_receipt,
            "host_seal": host_seal,
            "receipt": authorized.compiled.receipt,
            "result": authorized.compiled.result,
        },
    }


def verify_operation(request: dict[str, Any]) -> dict[str, Any]:
    if set(request) != {"action", "artifacts"}:
        raise PortfolioError("worker verify request has wrong key set")
    artifacts = decode_artifacts(request["artifacts"])
    trusted_now = now_utc()

    authority_value = load_json_bytes(
        artifacts["authority"], "upstream authority"
    )
    normalized_authority, canonical_authority = current.canonical_authority(
        authority_value
    )
    if artifacts["authority"] != canonical_authority:
        raise PortfolioError(
            "upstream authority: noncanonical persisted bytes"
        )

    host_before = host.load_host_authority(trusted_now)
    key = host_before.key
    floor_before = host_before.floor
    require_current_authority(floor_before, artifacts["authority"])
    require_authority_chronology(normalized_authority, floor_before, trusted_now)
    seal = host.parse_host_seal(artifacts["host_seal"])
    if seal["key_id"] != key.key_id:
        raise PortfolioError("host seal: key_id mismatch")
    result = load_json_bytes(artifacts["result"], "result")
    expected_bindings = {
        "authority_floor_generation": floor_before.generation,
        "authority_floor_sha256": host._digest(floor_before.raw),
        "authority_sha256": host._digest(artifacts["authority"]),
        "current_receipt_sha256": host._digest(artifacts["current_receipt"]),
        "evaluated_at": result.get("evaluated_at"),
        "input_sha256": result.get("input_sha256"),
        "key_id": key.key_id,
        "markdown_sha256": host._digest(artifacts["markdown"]),
        "receipt_file_sha256": host._digest(artifacts["receipt"]),
        "result_sha256": host._digest(artifacts["result"]),
        "schema": host.HOST_SEAL_SCHEMA,
    }
    base = {name: seal[name] for name in expected_bindings}
    if base != expected_bindings:
        raise PortfolioError(
            "host seal: exact compiled-generation/current-floor binding mismatch"
        )
    expected_mac = hmac.new(
        key.key, current._canonical(base), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(seal["hmac_sha256"], expected_mac):
        raise PortfolioError("host seal: HMAC mismatch")

    verified = current.verify_authorized_at(
        artifacts["result"],
        artifacts["markdown"],
        artifacts["receipt"],
        artifacts["authority"],
        artifacts["current_receipt"],
        key,
        trusted_now,
    )
    host_after = host.load_host_authority(trusted_now)
    host.same_host_authority(host_before, host_after)
    require_current_authority(host_after.floor, artifacts["authority"])
    require_authority_chronology(
        normalized_authority, host_after.floor, trusted_now
    )
    return {
        "ok": True,
        "verified": {
            **verified,
            "authority_floor_generation": host_after.floor.generation,
            "authority_floor_sha256": host._digest(host_after.floor.raw),
            "host_seal_sha256": host._digest(artifacts["host_seal"]),
            "host_seal_verified": True,
        },
    }
