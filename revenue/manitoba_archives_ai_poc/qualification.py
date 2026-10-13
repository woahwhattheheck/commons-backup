#!/usr/bin/env python3
"""Fail-closed qualification compiler for University of Manitoba IT-0280-2627-LB.

Public tender indexes may establish that a pursuit exists. They do not establish
controlling requirements, bidder eligibility, addenda, or submission authority.
The CLI therefore evaluates discovery evidence only. A trusted host may call
``evaluate_with_trusted_sources`` after independently recovering University/Euna
procurement bytes and binding them by SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RFP_ID = "IT-0280-2627-LB"
MERX_ID = "0000331062-MERX"
BUYER = "University of Manitoba"
TITLE = "IT Consulting Services for Archives AI Proof of Concept Project"
REPORTED_DEADLINE = "2026-09-25 (time/timezone unverified)"
TRUSTED_AUTHORITY = "UNIVERSITY_OR_EUNA_OFFICIAL"
ALLOWED_CLASSIFICATIONS = {"MANDATORY", "EVALUATED", "INFORMATIONAL"}
ALLOWED_EVIDENCE_STATES = {"PROVEN", "UNKNOWN", "MISSING", "OWNER_ATTESTATION_REQUIRED"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class QualificationError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require_str(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{key} must be a non-empty string")
    return value


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise QualificationError("deadline_utc must be canonical UTC with trailing Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise QualificationError("invalid deadline_utc") from exc
    if parsed.tzinfo != timezone.utc:
        raise QualificationError("deadline_utc must be UTC")
    return parsed


def _validate_notice(notice: Any) -> None:
    if not isinstance(notice, dict):
        raise QualificationError("notice must be an object")
    if notice.get("rfp_id") != RFP_ID:
        raise QualificationError("unexpected rfp_id")
    if notice.get("merx_notice_id") != MERX_ID:
        raise QualificationError("unexpected merx_notice_id")
    if notice.get("buyer") != BUYER:
        raise QualificationError("unexpected buyer")
    if notice.get("title") != TITLE:
        raise QualificationError("unexpected title")
    if notice.get("reported_deadline") != REPORTED_DEADLINE:
        raise QualificationError("unexpected reported deadline")
    sources = notice.get("discovery_sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise QualificationError("notice requires at least two discovery sources")
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
    for source in trusted_sources:
        if not isinstance(source, dict):
            raise QualificationError("trusted source must be an object")
        sid = _require_str(source, "source_id")
        if sid in by_id:
            raise QualificationError(f"duplicate trusted source_id: {sid}")
        sha = _require_str(source, "sha256")
        if not HEX64.fullmatch(sha):
            raise QualificationError(f"{sid}: sha256 must be lowercase 64-hex")
        if source.get("authority") != TRUSTED_AUTHORITY:
            raise QualificationError(f"{sid}: untrusted authority")
        current = source.get("current")
        complete = source.get("scope_complete")
        if not isinstance(current, bool) or not isinstance(complete, bool):
            raise QualificationError(f"{sid}: current/scope_complete must be booleans")
        kind = _require_str(source, "kind")
        if kind not in {"SOLICITATION", "ADDENDUM", "OFFICIAL_FORM", "OFFICIAL_QA"}:
            raise QualificationError(f"{sid}: invalid trusted source kind")
        locator = _require_str(source, "official_locator")
        if not locator.startswith(("https://", "http://")):
            raise QualificationError(f"{sid}: official_locator must be an absolute HTTP(S) URL")
        supersedes = source.get("supersedes", [])
        if not isinstance(supersedes, list) or any(not isinstance(v, str) or not v for v in supersedes):
            raise QualificationError(f"{sid}: supersedes must be a string list")
        if len(set(supersedes)) != len(supersedes):
            raise QualificationError(f"{sid}: duplicate supersedes entry")
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


def _validate_requirements(requirements: Any, trusted: dict[str, dict[str, Any]], evidence: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
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
            raise QualificationError(f"{rid}: evidence_ids must be a string list")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise QualificationError(f"{rid}: duplicate evidence_ids")
        for eid in evidence_ids:
            if eid not in evidence:
                raise QualificationError(f"{rid}: unknown evidence_id {eid}")
        normalized.append(req)
    return normalized


def _receipt(status: str, packet: dict[str, Any], errors: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "rfp_id": RFP_ID,
        "buyer": BUYER,
        "status": status,
        "packet_sha256": _canonical_json_sha(packet),
        "errors": errors,
        "authority": (
            "qualification evidence only; no buyer contact, procurement registration, legal/privacy/eligibility "
            "representation, pricing commitment, submission, signature, contract, award, payment, production "
            "deployment, or revenue authority"
        ),
        **extra,
    }


def evaluate_discovery(packet: dict[str, Any]) -> dict[str, Any]:
    """Production-safe discovery evaluator. Never accepts caller-minted trust."""
    try:
        _validate_notice(packet.get("notice"))
    except QualificationError as exc:
        return _receipt("INVALID", packet, [str(exc)])
    return _receipt(
        "HOLD_CONTROLLING_PACK_REQUIRED",
        packet,
        ["discovery records are non-controlling; recover University/Euna official package and all addenda"],
    )


def evaluate_with_trusted_sources(packet: dict[str, Any], trusted_sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Trusted-host boundary for independently acquired official procurement bytes."""
    try:
        _validate_notice(packet.get("notice"))
        trusted = _validate_trusted_sources(trusted_sources)
        current_solicitation = next(
            source
            for source in trusted.values()
            if source.get("current") is True
            and source.get("scope_complete") is True
            and source.get("kind") == "SOLICITATION"
        )
        deadline = _parse_utc(current_solicitation.get("deadline_utc"))
        if _utc_now() >= deadline:
            return _receipt(
                "HOLD_DEADLINE_REVERIFY",
                packet,
                ["controlling deadline reached; reverify current solicitation/addenda before any owner action"],
            )
        evidence = _validate_evidence(packet.get("evidence"))
        requirements = _validate_requirements(packet.get("requirements"), trusted, evidence)
    except (QualificationError, StopIteration) as exc:
        message = str(exc) if str(exc) else "missing current solicitation source"
        return _receipt("INVALID", packet, [message])

    if not requirements:
        return _receipt(
            "HOLD_REQUIREMENT_EXTRACTION_REQUIRED",
            packet,
            ["official package is bound but no source-linked requirements have been extracted"],
            trusted_source_count=len(trusted),
        )

    mandatory = [req for req in requirements if req["classification"] == "MANDATORY"]
    gaps: list[dict[str, Any]] = []
    for req in mandatory:
        ids = req.get("evidence_ids", [])
        states = [evidence[eid]["status"] for eid in ids]
        if not ids or any(state != "PROVEN" for state in states):
            gaps.append({"requirement_id": req["requirement_id"], "evidence_ids": ids, "states": states})
    if gaps:
        return _receipt(
            "HOLD_MANDATORY_GAPS",
            packet,
            [f"{len(gaps)} mandatory requirement(s) lack proven evidence"],
            mandatory_gaps=gaps,
            requirement_count=len(requirements),
        )

    return _receipt(
        "READY_FOR_OWNER_REVIEW",
        packet,
        [],
        requirement_count=len(requirements),
        mandatory_requirement_count=len(mandatory),
        evaluated_requirement_count=sum(req["classification"] == "EVALUATED" for req in requirements),
        submission_authorized=False,
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
