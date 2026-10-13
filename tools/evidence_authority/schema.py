"""Bounded candidate, manifest, and retained-record schemas."""

from __future__ import annotations

from typing import Any, Mapping

from .codec import (
    AUTHORITY_CLASSES,
    CLAIM_SCOPES,
    MAX_SOURCES,
    SCHEMA_CANDIDATE,
    SCHEMA_MANIFEST,
    SCHEMA_RECORD,
    GateError,
    bounded_payload,
    parse_ts,
    require_exact_keys,
    require_id,
    require_path,
    require_sha256,
    require_text,
    sha256_bytes,
    sha256_value,
)

_CANDIDATE_KEYS = {
    "schema",
    "claim_id",
    "issuer_id",
    "subject_id",
    "claim_kind",
    "claim_scope",
    "generation",
    "payload",
}
_MANIFEST_KEYS = {"schema", "generation", "sources"}
_SOURCE_KEYS = {"path", "sha256"}
_RECORD_KEYS = {
    "schema",
    "authority_class",
    "issuer_id",
    "subject_id",
    "claim_kind",
    "claim_scope",
    "generation",
    "issued_at_utc",
    "valid_from_utc",
    "valid_until_utc",
    "payload",
}


def validate_candidate(raw: Any) -> dict[str, Any]:
    require_exact_keys(raw, _CANDIDATE_KEYS, "candidate")
    if raw["schema"] != SCHEMA_CANDIDATE:
        raise GateError("unsupported candidate schema")
    scope = require_text(raw["claim_scope"], "candidate.claim_scope")
    if scope not in CLAIM_SCOPES:
        raise GateError("candidate.claim_scope is not admitted")
    return {
        "schema": SCHEMA_CANDIDATE,
        "claim_id": require_id(raw["claim_id"], "candidate.claim_id"),
        "issuer_id": require_id(raw["issuer_id"], "candidate.issuer_id"),
        "subject_id": require_id(raw["subject_id"], "candidate.subject_id"),
        "claim_kind": require_id(raw["claim_kind"], "candidate.claim_kind"),
        "claim_scope": scope,
        "generation": require_id(raw["generation"], "candidate.generation"),
        "payload": bounded_payload(raw["payload"], "candidate.payload"),
    }


def validate_manifest(raw: Any) -> dict[str, Any]:
    require_exact_keys(raw, _MANIFEST_KEYS, "manifest")
    if raw["schema"] != SCHEMA_MANIFEST:
        raise GateError("unsupported manifest schema")
    generation = require_id(raw["generation"], "manifest.generation")
    rows = raw["sources"]
    if type(rows) is not list:
        raise GateError("manifest.sources must be an array")
    if not rows:
        raise GateError("manifest.sources must be non-empty")
    if len(rows) > MAX_SOURCES:
        raise GateError("manifest.sources exceeds bound")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for i, row in enumerate(rows):
        require_exact_keys(row, _SOURCE_KEYS, f"manifest.sources[{i}]")
        path = require_path(row["path"], f"manifest.sources[{i}].path")
        digest = require_sha256(row["sha256"], f"manifest.sources[{i}].sha256")
        if path in seen:
            raise GateError("manifest.sources contains a duplicate path")
        seen.add(path)
        out.append({"path": path, "sha256": digest})
    ordered = sorted(out, key=lambda item: item["path"])
    if [item["path"] for item in rows] != [item["path"] for item in ordered]:
        raise GateError("manifest.sources must be sorted by path")
    return {"schema": SCHEMA_MANIFEST, "generation": generation, "sources": ordered}


def validate_record(raw: Any, *, path: str) -> dict[str, Any]:
    require_exact_keys(raw, _RECORD_KEYS, f"record[{path}]")
    if raw["schema"] != SCHEMA_RECORD:
        raise GateError(f"record[{path}] unsupported schema")
    authority = require_text(raw["authority_class"], f"record[{path}].authority_class")
    if authority not in AUTHORITY_CLASSES:
        raise GateError(f"record[{path}].authority_class is not admitted")
    scope = require_text(raw["claim_scope"], f"record[{path}].claim_scope")
    if scope not in CLAIM_SCOPES:
        raise GateError(f"record[{path}].claim_scope is not admitted")
    issued = parse_ts(raw["issued_at_utc"], f"record[{path}].issued_at_utc")
    valid_from = parse_ts(raw["valid_from_utc"], f"record[{path}].valid_from_utc")
    valid_until = parse_ts(raw["valid_until_utc"], f"record[{path}].valid_until_utc")
    if valid_from > valid_until:
        raise GateError(f"record[{path}] valid_from follows valid_until")
    if issued > valid_until:
        raise GateError(f"record[{path}] issued_at follows valid_until")
    return {
        "schema": SCHEMA_RECORD,
        "authority_class": authority,
        "issuer_id": require_id(raw["issuer_id"], f"record[{path}].issuer_id"),
        "subject_id": require_id(raw["subject_id"], f"record[{path}].subject_id"),
        "claim_kind": require_id(raw["claim_kind"], f"record[{path}].claim_kind"),
        "claim_scope": scope,
        "generation": require_id(raw["generation"], f"record[{path}].generation"),
        "issued_at_utc": raw["issued_at_utc"],
        "valid_from_utc": raw["valid_from_utc"],
        "valid_until_utc": raw["valid_until_utc"],
        "payload": bounded_payload(raw["payload"], f"record[{path}].payload"),
        "_path": path,
    }


def bind_sources(
    manifest: Mapping[str, Any],
    source_bytes: Mapping[str, bytes],
    *,
    _digest=sha256_bytes,
    _loads=None,
) -> list[dict[str, Any]]:
    """Closed inventory: exact path set, exact bytes, no aliases or remints."""
    from .codec import loads_strict_json

    parser = _loads or loads_strict_json
    if not isinstance(source_bytes, dict):
        raise GateError("retained sources must be a path-to-bytes mapping")
    expected = [row["path"] for row in manifest["sources"]]
    actual = list(source_bytes)
    if sorted(actual) != sorted(expected) or len(actual) != len(set(actual)):
        raise GateError("retained source inventory is not closed")
    if actual != expected:
        raise GateError("retained source order must match the closed manifest")
    records: list[dict[str, Any]] = []
    for row in manifest["sources"]:
        path = row["path"]
        payload = source_bytes[path]
        if type(payload) is not bytes:
            raise GateError(f"source[{path}] is not exact bytes")
        digest = _digest(payload)
        if digest != row["sha256"]:
            raise GateError(f"source[{path}] digest does not match retained bytes")
        records.append({**validate_record(parser(payload), path=path), "_sha256": digest})
    return records


def identity_tuple(obj: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        obj["issuer_id"],
        obj["subject_id"],
        obj["claim_kind"],
        obj["claim_scope"],
        obj["generation"],
    )


def payload_digest(obj: Mapping[str, Any], _hash=sha256_value) -> str:
    return _hash(obj["payload"])
