"""Deterministic qualification compiler for FSU / RFxPremier ITN 6769-4.

This module is offline decision support. It never logs into Jaggaer, registers a
supplier, contacts FSU/RFxPremier, submits a question/proposal, commits pricing,
signs certifications, spends money, accepts a contract, or recognizes revenue.

A readiness result requires two separate things:
1. a complete packet whose mandatory gates are bound to controlling sources; and
2. an out-of-band expected SHA-256 for the *normalized* source packet.

The expected digest is deliberately not stored inside the packet. That makes the
trust-root dependency explicit rather than letting a caller self-attest that its
own JSON is authoritative.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA = "commons.fsu-itn-6769-4-qualification/v1"
SOURCE_SCHEMA = "commons.fsu-itn-6769-4-source/v1"
RECEIPT_SCHEMA = "commons.fsu-itn-6769-4-receipt/v1"
OPPORTUNITY_ID = "FSU-ITN-6769-4"
MAX_TEXT = 512
SAFE_INT = 2**53 - 1
PACKAGE_INVENTORY_MAX_AGE_SECONDS = 24 * 60 * 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
ALLOWED_SOURCE_KINDS = {
    "PUBLIC_PORTAL",
    "PUBLIC_NOTICE",
    "CONTROLLING_ITN",
    "ATTACHMENT",
    "ADDENDUM",
    "Q_AND_A",
}
CONTROLLING_KINDS = {"CONTROLLING_ITN", "ATTACHMENT", "ADDENDUM", "Q_AND_A"}
ALLOWED_GATE_STATES = {"PROVEN", "PARTNER_CURABLE", "MISSING", "FAIL", "NOT_APPLICABLE"}
ALLOWED_ROUTE = {"PRIME", "TEAM", "BOTH"}
ALLOWED_SOURCE_HOSTS = {
    "bids.sciquest.com",
    "solutions.sciquest.com",
    "app01.jaggaer.com",
    "procurement.fsu.edu",
    "www.rfxpremier.org",
    "rfxpremier.org",
}
AUTHORITY_CEILING = {
    "portal_login": False,
    "supplier_registration": False,
    "buyer_contact": False,
    "question_submission": False,
    "pricing_commitment": False,
    "signature_or_certification": False,
    "proposal_submission": False,
    "spend": False,
    "contract_acceptance": False,
    "award_claim": False,
    "recognized_revenue": False,
}


class QualificationError(ValueError):
    pass


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise QualificationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    if not isinstance(text, str):
        raise QualificationError("JSON input must be text")

    def bad_constant(value: str) -> None:
        raise QualificationError(f"non-finite JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=_pairs_no_duplicates, parse_constant=bad_constant)
    except QualificationError:
        raise
    except Exception as exc:  # pragma: no cover - normalization below is stricter
        raise QualificationError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _expect_exact_keys(obj: Any, keys: set[str], where: str) -> None:
    if type(obj) is not dict:
        raise QualificationError(f"{where} must be object")
    got = set(obj)
    missing = keys - got
    extra = got - keys
    if missing or extra:
        raise QualificationError(f"{where} keys mismatch missing={sorted(missing)} extra={sorted(extra)}")


def _text(value: Any, where: str, *, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str or not value or len(value) > max_len or any(ord(c) < 32 for c in value):
        raise QualificationError(f"{where} must be bounded printable text")
    return value


def _id(value: Any, where: str) -> str:
    value = _text(value, where, max_len=128)
    if not ID_RE.fullmatch(value):
        raise QualificationError(f"{where} invalid identifier")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise QualificationError(f"{where} must be lowercase sha256")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise QualificationError(f"{where} must be boolean")
    return value


def parse_utc(value: Any, where: str) -> datetime:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise QualificationError(f"{where} must be canonical UTC seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise QualificationError(f"{where} invalid UTC") from exc


def _approved_url(value: Any, where: str) -> str:
    url = _text(value, where, max_len=500)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
        raise QualificationError(f"{where} must use approved https host")
    if host not in ALLOWED_SOURCE_HOSTS:
        raise QualificationError(f"{where} host is not approved")
    return url


def _normalize_source(row: Any, as_of: datetime) -> dict[str, Any]:
    keys = {"id", "kind", "url", "capturedAt", "contentSha256", "controlling", "label"}
    _expect_exact_keys(row, keys, "source")
    sid = _id(row["id"], "source.id")
    kind = _text(row["kind"], "source.kind", max_len=32)
    if kind not in ALLOWED_SOURCE_KINDS:
        raise QualificationError("source.kind unsupported")
    captured = parse_utc(row["capturedAt"], "source.capturedAt")
    if captured > as_of:
        raise QualificationError("future source capture")
    controlling = _bool(row["controlling"], "source.controlling")
    if controlling and kind not in CONTROLLING_KINDS:
        raise QualificationError("public notice/index source cannot be controlling")
    return {
        "id": sid,
        "kind": kind,
        "url": _approved_url(row["url"], "source.url"),
        "capturedAt": row["capturedAt"],
        "contentSha256": _sha(row["contentSha256"], "source.contentSha256"),
        "controlling": controlling,
        "label": _text(row["label"], "source.label"),
    }


def _normalize_gate(row: Any, source_ids: set[str]) -> dict[str, Any]:
    keys = {"id", "category", "requirement", "route", "state", "sourceId", "evidenceSha256", "partnerEvidenceSha256"}
    _expect_exact_keys(row, keys, "gate")
    state = _text(row["state"], "gate.state", max_len=32)
    if state not in ALLOWED_GATE_STATES:
        raise QualificationError("gate.state unsupported")
    route = _text(row["route"], "gate.route", max_len=8)
    if route not in ALLOWED_ROUTE:
        raise QualificationError("gate.route unsupported")
    source_id = _id(row["sourceId"], "gate.sourceId")
    if source_id not in source_ids:
        raise QualificationError("gate.sourceId unknown")
    evidence = row["evidenceSha256"]
    partner = row["partnerEvidenceSha256"]
    if state == "PROVEN":
        _sha(evidence, "gate.evidenceSha256")
    elif evidence is not None:
        _sha(evidence, "gate.evidenceSha256")
    if state == "PARTNER_CURABLE":
        _sha(partner, "gate.partnerEvidenceSha256")
    elif partner is not None:
        _sha(partner, "gate.partnerEvidenceSha256")
    return {
        "id": _id(row["id"], "gate.id"),
        "category": _text(row["category"], "gate.category", max_len=64),
        "requirement": _text(row["requirement"], "gate.requirement", max_len=500),
        "route": route,
        "state": state,
        "sourceId": source_id,
        "evidenceSha256": evidence,
        "partnerEvidenceSha256": partner,
    }


def normalize_source_packet(packet: Any, *, as_of: str) -> dict[str, Any]:
    now = parse_utc(as_of, "as_of")
    keys = {
        "schema", "opportunityId", "buyer", "solicitationId", "title",
        "openAt", "closeAt", "deadlineSourceId", "sources", "packetManifest",
        "serviceCategories", "mandatoryGates", "notes",
    }
    _expect_exact_keys(packet, keys, "packet")
    if packet["schema"] != SOURCE_SCHEMA:
        raise QualificationError("wrong source schema")
    if packet["opportunityId"] != OPPORTUNITY_ID or packet["solicitationId"] != "ITN 6769-4":
        raise QualificationError("wrong opportunity identity")
    open_at = parse_utc(packet["openAt"], "openAt")
    close_at = parse_utc(packet["closeAt"], "closeAt")
    if close_at <= open_at:
        raise QualificationError("closeAt must follow openAt")

    if type(packet["sources"]) is not list or not packet["sources"]:
        raise QualificationError("sources required")
    sources = [_normalize_source(x, now) for x in packet["sources"]]
    if len({x["id"] for x in sources}) != len(sources):
        raise QualificationError("duplicate source id")
    source_ids = {x["id"] for x in sources}
    deadline_source_id = _id(packet["deadlineSourceId"], "deadlineSourceId")
    if deadline_source_id not in source_ids:
        raise QualificationError("deadlineSourceId unknown")

    manifest = packet["packetManifest"]
    _expect_exact_keys(manifest, {"complete", "files", "addendaCheckedThrough", "authRequiredForFullPacket"}, "packetManifest")
    complete = _bool(manifest["complete"], "packetManifest.complete")
    auth_required = _bool(manifest["authRequiredForFullPacket"], "packetManifest.authRequiredForFullPacket")
    checked = parse_utc(manifest["addendaCheckedThrough"], "packetManifest.addendaCheckedThrough")
    if checked > now:
        raise QualificationError("future addenda check")
    if complete and auth_required:
        raise QualificationError("complete manifest cannot claim full packet still auth-blocked")
    if type(manifest["files"]) is not list:
        raise QualificationError("packetManifest.files must be list")
    files: list[dict[str, Any]] = []
    seen_files: set[str] = set()
    for row in manifest["files"]:
        _expect_exact_keys(row, {"sourceId", "filename", "sha256"}, "packetManifest.file")
        sid = _id(row["sourceId"], "packetManifest.file.sourceId")
        if sid not in source_ids:
            raise QualificationError("manifest file source unknown")
        filename = _text(row["filename"], "packetManifest.file.filename", max_len=200)
        if "/" in filename or "\\" in filename or filename in seen_files or filename in {".", ".."}:
            raise QualificationError("manifest filename invalid/duplicate")
        seen_files.add(filename)
        file_sha = _sha(row["sha256"], "packetManifest.file.sha256")
        source = next(x for x in sources if x["id"] == sid)
        if file_sha != source["contentSha256"]:
            raise QualificationError("manifest file sha must match bound source contentSha256")
        files.append({"sourceId": sid, "filename": filename, "sha256": file_sha})

    categories = packet["serviceCategories"]
    if type(categories) is not list or any(type(x) is not str for x in categories):
        raise QualificationError("serviceCategories must be string list")
    categories = sorted(set(_text(x, "serviceCategory", max_len=120) for x in categories))

    if type(packet["mandatoryGates"]) is not list:
        raise QualificationError("mandatoryGates must be list")
    gates = [_normalize_gate(x, source_ids) for x in packet["mandatoryGates"]]
    if len({x["id"] for x in gates}) != len(gates):
        raise QualificationError("duplicate gate id")

    return {
        "schema": SOURCE_SCHEMA,
        "opportunityId": OPPORTUNITY_ID,
        "buyer": _text(packet["buyer"], "buyer", max_len=120),
        "solicitationId": "ITN 6769-4",
        "title": _text(packet["title"], "title", max_len=200),
        "openAt": packet["openAt"],
        "closeAt": packet["closeAt"],
        "deadlineSourceId": deadline_source_id,
        "sources": sorted(sources, key=lambda x: x["id"]),
        "packetManifest": {
            "complete": complete,
            "files": sorted(files, key=lambda x: (x["filename"], x["sourceId"])),
            "addendaCheckedThrough": manifest["addendaCheckedThrough"],
            "authRequiredForFullPacket": auth_required,
        },
        "serviceCategories": categories,
        "mandatoryGates": sorted(gates, key=lambda x: x["id"]),
        "notes": _text(packet["notes"], "notes", max_len=1000),
    }


def normalized_source_sha256(packet: Any, *, as_of: str) -> str:
    return sha256_hex(canonical_bytes(normalize_source_packet(packet, as_of=as_of)))


def _packet_authoritative(packet: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    manifest = packet["packetManifest"]
    sources_by_id = {s["id"]: s for s in packet["sources"]}
    controlling_itn = [s for s in packet["sources"] if s["kind"] == "CONTROLLING_ITN" and s["controlling"]]
    if not manifest["complete"]:
        reasons.append("RAW_PACKET_MANIFEST_INCOMPLETE")
    if not controlling_itn:
        reasons.append("CONTROLLING_ITN_NOT_ACQUIRED")
    if not manifest["files"]:
        reasons.append("NO_CONTROLLING_FILES_HASH_BOUND")
    manifest_source_ids = {row["sourceId"] for row in manifest["files"]}
    for row in manifest["files"]:
        source = sources_by_id[row["sourceId"]]
        if source["kind"] not in CONTROLLING_KINDS or not source["controlling"]:
            reasons.append(f"MANIFEST_FILE_NOT_CONTROLLING:{row['filename']}")
    for source in packet["sources"]:
        if source["controlling"] and source["id"] not in manifest_source_ids:
            reasons.append(f"CONTROLLING_SOURCE_NOT_IN_MANIFEST:{source['id']}")
    deadline_source = sources_by_id[packet["deadlineSourceId"]]
    if deadline_source["kind"] not in CONTROLLING_KINDS or not deadline_source["controlling"]:
        reasons.append("DEADLINE_NOT_BOUND_TO_CONTROLLING_SOURCE")
    for gate in packet["mandatoryGates"]:
        source = sources_by_id[gate["sourceId"]]
        if source["kind"] not in CONTROLLING_KINDS or not source["controlling"]:
            reasons.append(f"GATE_NOT_BOUND_TO_CONTROLLING_SOURCE:{gate['id']}")
    return not reasons, sorted(set(reasons))


def _package_inventory_fresh(packet: dict[str, Any], now: datetime) -> bool:
    checked = parse_utc(packet["packetManifest"]["addendaCheckedThrough"], "packetManifest.addendaCheckedThrough")
    age_seconds = int((now - checked).total_seconds())
    return 0 <= age_seconds <= PACKAGE_INVENTORY_MAX_AGE_SECONDS

def compile_qualification(
    packet: Any,
    *,
    as_of: str,
    expected_source_packet_sha256: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_source_packet(packet, as_of=as_of)
    now = parse_utc(as_of, "as_of")
    close_at = parse_utc(normalized["closeAt"], "closeAt")
    source_digest = sha256_hex(canonical_bytes(normalized))
    authoritative, authority_reasons = _packet_authoritative(normalized)

    if expected_source_packet_sha256 is not None:
        _sha(expected_source_packet_sha256, "expected_source_packet_sha256")

    disposition = "HOLD_RAW_PACKET_REQUIRED"
    reasons = list(authority_reasons)

    # Ordering is authority-significant. A caller-authored deadline must never mint
    # a hard NO_BID before the complete packet is structurally authoritative, its
    # exact normalized digest is trusted out of band, and the addenda inventory is
    # current. This also prevents stale packets from asserting a deadline after a
    # possible unobserved extension.
    if not authoritative:
        pass
    elif expected_source_packet_sha256 is None:
        disposition = "HOLD_SOURCE_PACKET_TRUST_ROOT_REQUIRED"
        reasons = ["EXPECTED_SOURCE_PACKET_SHA256_REQUIRED_OUT_OF_BAND"]
    elif expected_source_packet_sha256 != source_digest:
        disposition = "HOLD_SOURCE_PACKET_TRUST_ROOT_MISMATCH"
        reasons = ["EXPECTED_SOURCE_PACKET_SHA256_MISMATCH"]
    elif not _package_inventory_fresh(normalized, now):
        disposition = "HOLD_PACKAGE_INVENTORY_STALE"
        reasons = ["ADDENDA_CHECK_EXCEEDS_24H_POLICY"]
    elif now >= close_at:
        disposition = "NO_BID_DEADLINE_CLOSED"
        reasons = ["TRUSTED_CURRENT_PACKET_PROPOSAL_DEADLINE_REACHED"]
    else:
        gates = normalized["mandatoryGates"]
        if not gates:
            disposition = "HOLD_MANDATORY_GATE_MATRIX_EMPTY"
            reasons = ["NO_MANDATORY_GATES_COMPILED"]
        else:
            hard_fail = [g["id"] for g in gates if g["state"] == "FAIL"]
            missing = [g["id"] for g in gates if g["state"] == "MISSING"]
            partner = [g["id"] for g in gates if g["state"] == "PARTNER_CURABLE"]
            if hard_fail:
                disposition = "NO_BID_MANDATORY_GATE_FAILED"
                reasons = [f"FAILED:{x}" for x in hard_fail]
            elif missing:
                disposition = "HOLD_MANDATORY_EVIDENCE_MISSING"
                reasons = [f"MISSING:{x}" for x in missing]
            elif partner:
                if normalized["serviceCategories"]:
                    disposition = "TEAMING_READY_FOR_OWNER_REVIEW"
                    reasons = [f"PARTNER_CURE_BOUND:{x}" for x in partner]
                else:
                    disposition = "HOLD_SERVICE_CATEGORIES_UNRESOLVED"
                    reasons = ["NO_SERVICE_CATEGORY_SELECTED"]
            elif normalized["serviceCategories"]:
                disposition = "PRIME_READY_FOR_OWNER_REVIEW"
                reasons = ["ALL_COMPILED_MANDATORY_GATES_PROVEN"]
            else:
                disposition = "HOLD_SERVICE_CATEGORIES_UNRESOLVED"
                reasons = ["NO_SERVICE_CATEGORY_SELECTED"]

    counts = {
        "sources": len(normalized["sources"]),
        "manifestFiles": len(normalized["packetManifest"]["files"]),
        "mandatoryGates": len(normalized["mandatoryGates"]),
        "provenGates": sum(1 for g in normalized["mandatoryGates"] if g["state"] == "PROVEN"),
        "partnerCurableGates": sum(1 for g in normalized["mandatoryGates"] if g["state"] == "PARTNER_CURABLE"),
        "missingGates": sum(1 for g in normalized["mandatoryGates"] if g["state"] == "MISSING"),
        "failedGates": sum(1 for g in normalized["mandatoryGates"] if g["state"] == "FAIL"),
    }
    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "opportunityId": OPPORTUNITY_ID,
        "sourcePacketSha256": source_digest,
        "trustedSourcePacketSha256": expected_source_packet_sha256,
        "evaluatedAt": as_of,
        "disposition": disposition,
        "reasons": sorted(reasons),
        "serviceCategories": normalized["serviceCategories"],
        "counts": counts,
        "policy": {"packageInventoryMaxAgeSeconds": PACKAGE_INVENTORY_MAX_AGE_SECONDS},
        "authority": AUTHORITY_CEILING,
    }
    receipt = dict(receipt_core)
    receipt["receiptSha256"] = sha256_hex(canonical_bytes(receipt_core))
    return {"schema": SCHEMA, "sourcePacket": normalized, "receipt": receipt}

def verify_qualification(
    packet: Any,
    receipt: Any,
    *,
    as_of: str,
    expected_source_packet_sha256: str | None = None,
) -> bool:
    compiled = compile_qualification(
        packet,
        as_of=as_of,
        expected_source_packet_sha256=expected_source_packet_sha256,
    )
    if type(receipt) is not dict:
        return False
    return canonical_bytes(compiled["receipt"]) == canonical_bytes(receipt)


def verify_current_qualification(
    packet: Any,
    receipt: Any,
    *,
    current_as_of: str,
    expected_source_packet_sha256: str | None = None,
) -> bool:
    """Verify the original receipt, then re-evaluate current time-sensitive state.

    Historical replay remains available through ``verify_qualification`` for tests
    and audit. This function is the current-work boundary: it refuses time travel
    and requires the disposition/reasons/policy to remain valid at trusted now.
    """
    if type(receipt) is not dict:
        return False
    evaluated_at = receipt.get("evaluatedAt")
    if type(evaluated_at) is not str:
        return False
    try:
        evaluated_dt = parse_utc(evaluated_at, "receipt.evaluatedAt")
        current_dt = parse_utc(current_as_of, "current_as_of")
    except QualificationError:
        return False
    if current_dt < evaluated_dt:
        return False
    if not verify_qualification(
        packet,
        receipt,
        as_of=evaluated_at,
        expected_source_packet_sha256=expected_source_packet_sha256,
    ):
        return False
    current = compile_qualification(
        packet,
        as_of=current_as_of,
        expected_source_packet_sha256=expected_source_packet_sha256,
    )["receipt"]
    semantic_keys = (
        "schema", "opportunityId", "sourcePacketSha256",
        "trustedSourcePacketSha256", "disposition", "reasons",
        "serviceCategories", "counts", "policy", "authority",
    )
    return all(receipt.get(key) == current.get(key) for key in semantic_keys)
