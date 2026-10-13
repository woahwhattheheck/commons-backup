"""Deterministic, authority-limited qualification for Loudoun Water RFP 2026-045-1400003."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "loudoun-lims-qualification/v1"
_ALLOWED_SOURCE_KINDS = {
    "OFFICIAL_PUBLIC_DETAIL",
    "SECONDARY_CURRENT_MIRROR",
    "STATE_INDEX",
    "INTERNAL_PRODUCT",
}
_ALLOWED_ACCESS = {"PUBLIC", "LOGIN_REQUIRED", "FORBIDDEN", "NOT_FOUND"}
_ALLOWED_GATE = {"NOT_EVIDENCED", "PROVISIONAL_UNVERIFIED", "EVIDENCED"}
_CORPORATE_GATES = {
    "three_public_us_water_wastewater_lims_implementations",
    "virginia_transaction_authority",
    "soc2_type_ii_or_equivalent",
    "technology_eo_and_cyber_insurance",
}


class QualificationError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _nonempty(value: Any, field: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise QualificationError(f"{field} must be a non-empty trimmed string")
    return value


def _strict_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise QualificationError(f"{field} must be a boolean")
    return value


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if type(manifest) is not dict:
        raise QualificationError("manifest must be an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise QualificationError("schema_version mismatch")
    if manifest.get("solicitation_id") != "2026-045-1400003":
        raise QualificationError("wrong solicitation_id")

    close = manifest.get("current_public_close")
    if type(close) is not dict:
        raise QualificationError("current_public_close must be an object")
    if close.get("at") != "2026-09-18T14:00:00-04:00":
        raise QualificationError("current public deadline must bind the Sep 18 extension")
    if close.get("authority") != "SECONDARY_CURRENT_MIRROR":
        raise QualificationError("deadline authority must remain secondary until official addendum bytes are recovered")
    if _strict_bool(close.get("official_addendum_recovered"), "official_addendum_recovered"):
        raise QualificationError("official addendum is not recovered")

    sources = manifest.get("sources")
    if type(sources) is not list or not sources:
        raise QualificationError("sources must be a non-empty list")
    ids: set[str] = set()
    for i, src in enumerate(sources):
        if type(src) is not dict:
            raise QualificationError(f"sources[{i}] must be an object")
        sid = _nonempty(src.get("id"), f"sources[{i}].id")
        if sid in ids:
            raise QualificationError(f"duplicate source id: {sid}")
        ids.add(sid)
        if src.get("kind") not in _ALLOWED_SOURCE_KINDS:
            raise QualificationError(f"invalid source kind: {sid}")
        if src.get("access") not in _ALLOWED_ACCESS:
            raise QualificationError(f"invalid source access: {sid}")
        _nonempty(src.get("locator"), f"sources[{i}].locator")
        _nonempty(src.get("observed_at"), f"sources[{i}].observed_at")

    attachments = manifest.get("official_attachments")
    if type(attachments) is not list or len(attachments) != 4:
        raise QualificationError("official_attachments must describe RFP, cost, RTM, and addendum")
    expected = {"rfp", "cost_proposal", "rtm", "addendum_1_qa"}
    seen = set()
    for i, item in enumerate(attachments):
        if type(item) is not dict:
            raise QualificationError(f"official_attachments[{i}] must be an object")
        aid = _nonempty(item.get("id"), f"official_attachments[{i}].id")
        seen.add(aid)
        if item.get("access") not in {"LOGIN_REQUIRED", "NOT_FOUND"}:
            raise QualificationError(f"{aid} must remain inaccessible without authenticated action")
        if item.get("sha256") is not None:
            raise QualificationError(f"{aid} cannot have a hash before official bytes are recovered")
        if item.get("official_bytes_recovered") is not False:
            raise QualificationError(f"{aid} cannot claim recovered official bytes")
    if seen != expected:
        raise QualificationError("official attachment inventory mismatch")

    gates = manifest.get("qualification_gates")
    if type(gates) is not list or not gates:
        raise QualificationError("qualification_gates must be a non-empty list")
    gate_ids = set()
    for i, gate in enumerate(gates):
        if type(gate) is not dict:
            raise QualificationError(f"qualification_gates[{i}] must be an object")
        gid = _nonempty(gate.get("id"), f"qualification_gates[{i}].id")
        if gid in gate_ids:
            raise QualificationError(f"duplicate gate id: {gid}")
        gate_ids.add(gid)
        state = gate.get("evidence_status")
        if state not in _ALLOWED_GATE:
            raise QualificationError(f"invalid gate state: {gid}")
        basis = gate.get("basis")
        if basis not in {"SECONDARY_ONLY", "INTERNAL_PRODUCT_ONLY", "OFFICIAL_BYTES"}:
            raise QualificationError(f"invalid gate basis: {gid}")
        refs = gate.get("evidence_refs")
        if type(refs) is not list or any(type(x) is not str or x not in ids for x in refs):
            raise QualificationError(f"bad evidence_refs: {gid}")
        if gid in _CORPORATE_GATES and state == "EVIDENCED":
            if basis != "OFFICIAL_BYTES":
                raise QualificationError(f"corporate gate {gid} cannot be evidenced by {basis}")
    missing = _CORPORATE_GATES - gate_ids
    if missing:
        raise QualificationError(f"missing corporate gates: {sorted(missing)}")

    authority = manifest.get("authority")
    if type(authority) is not dict:
        raise QualificationError("authority must be an object")
    for key in (
        "ionwave_login",
        "registration",
        "terms_acceptance",
        "buyer_contact",
        "partner_contact",
        "proposal_upload",
        "pricing_commitment",
        "submission",
        "award_claim",
        "revenue_claim",
    ):
        if authority.get(key) is not False:
            raise QualificationError(f"authority.{key} must be false")
    return manifest


def validate_partner_packet(packet: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    if type(packet) is not dict:
        raise QualificationError("partner packet must be an object")
    if packet.get("schema_version") != SCHEMA_VERSION:
        raise QualificationError("partner schema mismatch")
    if packet.get("solicitation_id") != manifest["solicitation_id"]:
        raise QualificationError("partner solicitation mismatch")
    if packet.get("product_evidence_ref") != "aquatrace_main":
        raise QualificationError("partner packet must bind exact AquaTrace source reference")
    capabilities = packet.get("bounded_workshare")
    if type(capabilities) is not list or len(capabilities) < 5:
        raise QualificationError("bounded_workshare is incomplete")
    for i, row in enumerate(capabilities):
        if type(row) is not dict:
            raise QualificationError(f"bounded_workshare[{i}] must be an object")
        _nonempty(row.get("capability"), f"bounded_workshare[{i}].capability")
        _nonempty(row.get("evidence"), f"bounded_workshare[{i}].evidence")
        if row.get("claim_level") not in {"IMPLEMENTED_PRODUCT_SOURCE", "PRODUCTION_GATE_REQUIRED"}:
            raise QualificationError(f"invalid workshare claim level at {i}")
    forbidden = packet.get("must_not_represent")
    if type(forbidden) is not list or not {
        "three_completed_public_utility_lims_implementations",
        "soc2_certification",
        "virginia_transaction_authority",
        "required_insurance",
        "buyer_acceptance",
        "award",
    }.issubset(set(forbidden)):
        raise QualificationError("must_not_represent is incomplete")
    return packet


def compile_decision(manifest: dict[str, Any], partner_packet: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    validate_partner_packet(partner_packet, manifest)

    official_ready = all(
        item["official_bytes_recovered"] and item["sha256"]
        for item in manifest["official_attachments"]
    )
    corporate_ready = all(
        gate["evidence_status"] == "EVIDENCED"
        for gate in manifest["qualification_gates"]
        if gate["id"] in _CORPORATE_GATES
    )

    if official_ready and corporate_ready:
        posture = "PRIME_ELIGIBLE"
        blocker = None
    elif partner_packet["bounded_workshare"]:
        posture = "TEAMING_ONLY"
        blocker = "OFFICIAL_PACKAGE_AND_PRIME_CORPORATE_EVIDENCE_REQUIRED"
    else:
        posture = "NO_BID"
        blocker = "NO_VERIFIABLE_WORKSHARE"

    source_snapshot = {
        "manifest": manifest,
        "partner_packet": partner_packet,
    }
    core = {
        "schema_version": SCHEMA_VERSION,
        "solicitation_id": manifest["solicitation_id"],
        "posture": posture,
        "blocker": blocker,
        "official_package_complete": official_ready,
        "corporate_prime_gates_complete": corporate_ready,
        "current_public_close": manifest["current_public_close"]["at"],
        "outbound_authorized": False,
        "submission_authorized": False,
        "source_sha256": _sha(source_snapshot),
    }
    return {**core, "receipt_sha256": _sha(core)}


def verify_decision(
    manifest: dict[str, Any],
    partner_packet: dict[str, Any],
    decision: dict[str, Any],
) -> bool:
    if type(decision) is not dict:
        return False
    try:
        return decision == compile_decision(manifest, partner_packet)
    except (QualificationError, TypeError, ValueError):
        return False
