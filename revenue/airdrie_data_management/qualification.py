#!/usr/bin/env python3
"""Fail-closed qualification compiler for City of Airdrie AB-2026-06233.

Discovery records can establish that a pursuit exists; they cannot establish
controlling bid requirements. The production CLI intentionally has no way to
supply trusted controlling-source authority. The trusted-host integration path
requires a host-retained HMAC capability loaded from process configuration;
that capability is never accepted from packet bytes, caller source claims, or
CLI arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOLICITATION_ID = "AB-2026-06233"
BUYER = "City of Airdrie"
TITLE = "Data Management Consultant"
REPORTED_DEADLINE_LOCAL = "2026-10-06 20:00 (timezone unverified)"
ALLOWED_CLASSIFICATIONS = {"MANDATORY", "EVALUATED", "INFORMATIONAL"}
ALLOWED_EVIDENCE_STATES = {"PROVEN", "UNKNOWN", "MISSING", "OWNER_ATTESTATION_REQUIRED"}
TRUSTED_AUTHORITY = "CITY_OR_OFFICIAL_PROCUREMENT_PORTAL"
AUTHORITY_SCHEMA = "airdrie-controlling-source-authority/v1"
AUTHORITY_KEY_ID = "airdrie-host-v1"
AUTHORITY_KEY_ENV = "AIRDRIE_CONTROLLING_AUTHORITY_KEY_HEX"
MIN_AUTHORITY_KEY_BYTES = 32
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class QualificationError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise QualificationError("timestamp must be canonical UTC with trailing Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise QualificationError("invalid UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise QualificationError("timestamp must be UTC")
    return parsed


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_json(obj: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(obj)).hexdigest()


def _require_str(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{key} must be a non-empty string")
    return value


def _validate_notice(notice: Any) -> None:
    if not isinstance(notice, dict):
        raise QualificationError("notice must be an object")
    if notice.get("solicitation_id") != SOLICITATION_ID:
        raise QualificationError("unexpected solicitation_id")
    if notice.get("buyer") != BUYER:
        raise QualificationError("unexpected buyer")
    if notice.get("title") != TITLE:
        raise QualificationError("unexpected title")
    if notice.get("reported_deadline_local") != REPORTED_DEADLINE_LOCAL:
        raise QualificationError("unexpected reported deadline")
    sources = notice.get("discovery_sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise QualificationError("notice requires at least two independent discovery sources")
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise QualificationError("discovery source must be an object")
        uri = _require_str(source, "uri")
        _require_str(source, "source_type")
        if uri in seen:
            raise QualificationError("duplicate discovery source")
        seen.add(uri)


def _validate_trusted_sources(trusted_sources: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(trusted_sources, list) or not trusted_sources:
        raise QualificationError("trusted_sources must be a non-empty list")
    by_id: dict[str, dict[str, Any]] = {}
    current_complete_solicitations = 0
    allowed_keys = {
        "source_id",
        "sha256",
        "authority",
        "current",
        "scope_complete",
        "deadline_utc",
        "kind",
        "supersedes",
    }
    for source in trusted_sources:
        if not isinstance(source, dict):
            raise QualificationError("trusted source must be an object")
        unknown = set(source) - allowed_keys
        if unknown:
            raise QualificationError(f"trusted source has unknown field(s): {sorted(unknown)}")
        sid = _require_str(source, "source_id")
        if sid in by_id:
            raise QualificationError(f"duplicate trusted source_id: {sid}")
        sha = _require_str(source, "sha256")
        if not HEX64.fullmatch(sha):
            raise QualificationError(f"{sid}: sha256 must be lowercase 64-hex")
        if source.get("authority") != TRUSTED_AUTHORITY:
            raise QualificationError(f"{sid}: untrusted authority claim")
        current = source.get("current")
        complete = source.get("scope_complete")
        if type(current) is not bool or type(complete) is not bool:
            raise QualificationError(f"{sid}: current/scope_complete must be booleans")
        kind = _require_str(source, "kind")
        supersedes = source.get("supersedes", [])
        if not isinstance(supersedes, list) or any(not isinstance(v, str) or not v for v in supersedes):
            raise QualificationError(f"{sid}: supersedes must be string list")
        if len(set(supersedes)) != len(supersedes):
            raise QualificationError(f"{sid}: duplicate supersedes")
        deadline = source.get("deadline_utc")
        if deadline is not None:
            _parse_utc(deadline)
        if kind == "SOLICITATION" and deadline is None:
            raise QualificationError(f"{sid}: SOLICITATION requires deadline_utc")
        if current and complete and kind == "SOLICITATION":
            current_complete_solicitations += 1
        by_id[sid] = source
    for sid, source in by_id.items():
        for old in source.get("supersedes", []):
            if old not in by_id:
                raise QualificationError(f"{sid}: supersedes missing source {old}")
            if by_id[old].get("current") is True:
                raise QualificationError(f"{sid}: superseded source {old} still marked current")
    if current_complete_solicitations != 1:
        raise QualificationError("exactly one current scope-complete SOLICITATION source is required")
    return by_id


def _source_authority_projection(source: dict[str, Any]) -> dict[str, Any]:
    """Canonical semantics authenticated by the host capability."""
    return {
        "authority": source["authority"],
        "current": source["current"],
        "deadline_utc": source.get("deadline_utc"),
        "kind": source["kind"],
        "scope_complete": source["scope_complete"],
        "sha256": source["sha256"],
        "source_id": source["source_id"],
        "supersedes": sorted(source.get("supersedes", [])),
    }


def _authority_payload(trusted: dict[str, dict[str, Any]], issued_at: str) -> dict[str, Any]:
    return {
        "schema": AUTHORITY_SCHEMA,
        "key_id": AUTHORITY_KEY_ID,
        "solicitation_id": SOLICITATION_ID,
        "issued_at": issued_at,
        "sources": [
            _source_authority_projection(trusted[sid])
            for sid in sorted(trusted)
        ],
    }


def _load_host_authority_key() -> bytes:
    raw = os.environ.get(AUTHORITY_KEY_ENV)
    if raw is None:
        raise QualificationError("host controlling-source authority capability is not provisioned")
    if not isinstance(raw, str) or len(raw) % 2:
        raise QualificationError("host authority capability must be lowercase hex")
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise QualificationError("host authority capability must be lowercase hex") from exc
    if raw != raw.lower() or key.hex() != raw:
        raise QualificationError("host authority capability must be canonical lowercase hex")
    if len(key) < MIN_AUTHORITY_KEY_BYTES:
        raise QualificationError(f"host authority capability must be at least {MIN_AUTHORITY_KEY_BYTES} bytes")
    return key


def issue_host_authority_set(
    trusted_sources: list[dict[str, Any]],
    *,
    issued_at: str,
) -> dict[str, Any]:
    """Trusted-host helper.

    This function can only mint an authority set when the host process has the
    out-of-band capability in ``AIRDRIE_CONTROLLING_AUTHORITY_KEY_HEX``. The
    key is not accepted through the packet, source list, authority document, or
    CLI. Treat code/process access that can read this capability as trusted-host
    authority; untrusted request data must never control that environment.
    """
    trusted = _validate_trusted_sources(trusted_sources)
    issued = _parse_utc(issued_at)
    if issued > _utc_now():
        raise QualificationError("host authority issued_at cannot be in the future")
    payload = _authority_payload(trusted, issued_at)
    key = _load_host_authority_key()
    mac = hmac.new(key, _canonical_json_bytes(payload), hashlib.sha256).hexdigest()
    return {**payload, "mac_sha256": mac}


def _verify_host_authority_set(
    authority_set: Any,
    trusted: dict[str, dict[str, Any]],
) -> str:
    if not isinstance(authority_set, dict):
        raise QualificationError("authority_set must be an object")
    expected_fields = {"schema", "key_id", "solicitation_id", "issued_at", "sources", "mac_sha256"}
    if set(authority_set) != expected_fields:
        raise QualificationError("authority_set fields do not match the v1 schema")
    if authority_set.get("schema") != AUTHORITY_SCHEMA:
        raise QualificationError("unsupported authority_set schema")
    if authority_set.get("key_id") != AUTHORITY_KEY_ID:
        raise QualificationError("unexpected authority key_id")
    if authority_set.get("solicitation_id") != SOLICITATION_ID:
        raise QualificationError("authority_set solicitation_id mismatch")
    issued_at = _require_str(authority_set, "issued_at")
    if _parse_utc(issued_at) > _utc_now():
        raise QualificationError("authority_set issued_at cannot be in the future")
    expected_payload = _authority_payload(trusted, issued_at)
    if authority_set.get("sources") != expected_payload["sources"]:
        raise QualificationError("authority_set does not bind the exact trusted-source generation")
    supplied_mac = _require_str(authority_set, "mac_sha256")
    if not HEX64.fullmatch(supplied_mac):
        raise QualificationError("authority_set mac_sha256 must be lowercase 64-hex")
    key = _load_host_authority_key()
    expected_mac = hmac.new(key, _canonical_json_bytes(expected_payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_mac, expected_mac):
        raise QualificationError("authority_set MAC verification failed")
    return _sha256_json(authority_set)


def _validate_evidence(evidence: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(evidence, list):
        raise QualificationError("evidence must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, dict):
            raise QualificationError("evidence item must be an object")
        eid = _require_str(item, "evidence_id")
        if eid in by_id:
            raise QualificationError(f"duplicate evidence_id: {eid}")
        state = item.get("status")
        if state not in ALLOWED_EVIDENCE_STATES:
            raise QualificationError(f"{eid}: invalid evidence status")
        if state == "PROVEN":
            _require_str(item, "artifact_ref")
            sha = _require_str(item, "artifact_sha256")
            if not HEX64.fullmatch(sha):
                raise QualificationError(f"{eid}: artifact_sha256 must be lowercase 64-hex")
        by_id[eid] = item
    return by_id


def _validate_requirements(
    requirements: Any,
    trusted: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(requirements, list):
        raise QualificationError("requirements must be a list")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for req in requirements:
        if not isinstance(req, dict):
            raise QualificationError("requirement must be an object")
        rid = _require_str(req, "requirement_id")
        if rid in seen:
            raise QualificationError(f"duplicate requirement_id: {rid}")
        seen.add(rid)
        source_id = _require_str(req, "source_id")
        source_sha = _require_str(req, "source_sha256")
        source = trusted.get(source_id)
        if source is None:
            raise QualificationError(f"{rid}: unknown trusted source")
        if source.get("current") is not True:
            raise QualificationError(f"{rid}: requirement cites superseded source")
        if source.get("sha256") != source_sha:
            raise QualificationError(f"{rid}: source sha mismatch")
        classification = req.get("classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise QualificationError(f"{rid}: invalid classification")
        _require_str(req, "locator")
        _require_str(req, "text")
        evidence_ids = req.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or any(not isinstance(v, str) or not v for v in evidence_ids):
            raise QualificationError(f"{rid}: evidence_ids must be string list")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise QualificationError(f"{rid}: duplicate evidence_ids")
        for eid in evidence_ids:
            if eid not in evidence:
                raise QualificationError(f"{rid}: unknown evidence_id {eid}")
        normalized.append(req)
    return normalized


def _receipt(status: str, packet: dict[str, Any], errors: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "solicitation_id": SOLICITATION_ID,
        "buyer": BUYER,
        "status": status,
        "packet_sha256": _sha256_json(packet),
        "errors": errors,
        "authority": (
            "qualification evidence only; no buyer contact, registration, certification, "
            "submission, pricing commitment, contract, award, payment, deployment, or revenue authority"
        ),
        **extra,
    }


def evaluate_discovery(packet: dict[str, Any]) -> dict[str, Any]:
    """Production-safe discovery path. It can never accept controlling-source authority."""
    try:
        _validate_notice(packet.get("notice"))
    except QualificationError as exc:
        return _receipt("INVALID", packet, [str(exc)])
    return _receipt(
        "HOLD_CONTROLLING_PACK_REQUIRED",
        packet,
        ["discovery records are non-controlling; recover City/official-procurement package and amendments"],
    )


def evaluate_with_trusted_sources(
    packet: dict[str, Any],
    trusted_sources: list[dict[str, Any]],
    authority_set: dict[str, Any],
) -> dict[str, Any]:
    """Trusted-host API with an out-of-band capability boundary.

    Callers may supply source *claims* and a candidate authority document, but
    neither can establish trust. Promotion requires an HMAC over the exact
    canonical source generation under a host-retained capability loaded from
    process configuration. The public CLI never loads or exposes this path.
    """
    try:
        _validate_notice(packet.get("notice"))
        trusted = _validate_trusted_sources(trusted_sources)
        authority_sha = _verify_host_authority_set(authority_set, trusted)
        current_solicitation = next(
            source for source in trusted.values()
            if source.get("current") is True
            and source.get("scope_complete") is True
            and source.get("kind") == "SOLICITATION"
        )
        deadline_utc = _require_str(current_solicitation, "deadline_utc")
        authority_extra = {
            "trusted_authority_schema": AUTHORITY_SCHEMA,
            "trusted_authority_key_id": AUTHORITY_KEY_ID,
            "trusted_authority_sha256": authority_sha,
            "trusted_authority_issued_at": authority_set["issued_at"],
        }
        if _utc_now() >= _parse_utc(deadline_utc):
            return _receipt(
                "HOLD_DEADLINE_REVERIFY",
                packet,
                ["controlling solicitation deadline reached; reverify amendment/currentness before proceeding"],
                **authority_extra,
            )
        evidence = _validate_evidence(packet.get("evidence"))
        requirements = _validate_requirements(packet.get("requirements"), trusted, evidence)
    except QualificationError as exc:
        return _receipt("INVALID", packet, [str(exc)])

    if not requirements:
        return _receipt(
            "HOLD_REQUIREMENT_EXTRACTION_REQUIRED",
            packet,
            ["trusted solicitation recovered but no sourced requirements have been extracted"],
            trusted_source_count=len(trusted),
            **authority_extra,
        )

    mandatory = [r for r in requirements if r["classification"] == "MANDATORY"]
    gaps: list[dict[str, Any]] = []
    for req in mandatory:
        ids = req.get("evidence_ids", [])
        states = [evidence[eid]["status"] for eid in ids]
        if not ids or any(state != "PROVEN" for state in states):
            gaps.append(
                {
                    "requirement_id": req["requirement_id"],
                    "evidence_ids": ids,
                    "states": states,
                }
            )
    if gaps:
        return _receipt(
            "HOLD_MANDATORY_GAPS",
            packet,
            [f"{len(gaps)} mandatory requirement(s) lack proven evidence"],
            mandatory_gaps=gaps,
            requirement_count=len(requirements),
            **authority_extra,
        )

    return _receipt(
        "READY_FOR_OWNER_REVIEW",
        packet,
        [],
        requirement_count=len(requirements),
        mandatory_requirement_count=len(mandatory),
        evaluated_requirement_count=sum(r["classification"] == "EVALUATED" for r in requirements),
        submission_authorized=False,
        **authority_extra,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    args = parser.parse_args(argv)
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID", "errors": [str(exc)]}, sort_keys=True))
        return 2
    if not isinstance(packet, dict):
        print(json.dumps({"status": "INVALID", "errors": ["packet root must be object"]}, sort_keys=True))
        return 2
    receipt = evaluate_discovery(packet)
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0 if receipt["status"].startswith("HOLD_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
