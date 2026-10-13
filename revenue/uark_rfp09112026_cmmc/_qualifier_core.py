#!/usr/bin/env python3
"""Fail-closed qualification compiler for UArk RFP09112026.

This module is an internal decision artifact. It never submits a proposal, contacts
a buyer/partner, asserts CMMC certification, or authorizes handling of FCI/CUI.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from typing import Any

SCHEMA = "uark-rfp09112026-cmmc-qualification/v1"
PACKET_SCHEMA = "uark-rfp09112026-cmmc-qualification-packet/v1"
OPERATION = "UARK-RFP09112026-CMMC-TEAMING-ZNCR8L4-20260914"
OWNER = "Z-NiobiumCauseway-2026-R8L4"
MODEL = "GPT-5.6 Sol"
RFP_NUMBER = "09112026"
RFP_URL = "https://hogbid.uark.edu/RFP09112026_Document.pdf"
HOGBID_URL = "https://hogbid.uark.edu/"
QUESTION_DEADLINE_UTC = "2026-09-25T22:00:00Z"  # 5:00 PM Central Daylight Time
PROPOSAL_DEADLINE_UTC = "2026-10-16T19:30:00Z"  # 2:30 PM Central Daylight Time
LAST_PLANNED_ADDENDUM_DATE = "2026-10-05"
INTERNAL_WORKSHARE_TARGET_USD = 35000
PRICE_BOUNDARY = "INTERNAL_HYPOTHESIS_NOT_OFFERED"

EXPECTED_SOURCE_GENERATION = {
    "rfp_number": RFP_NUMBER,
    "hogbid_url": HOGBID_URL,
    "rfp_url": RFP_URL,
    "rfp_content_acquired": True,
    "rfp_page_count": 31,
    "standard_terms_state": "LISTED_NOT_ACQUIRED",
    "addenda_state": "NONE_LISTED",
    "hogbid_checked_at_utc": "2026-09-15T00:58:00Z",
}
ALLOWED_ROUTES = frozenset({"PRIME", "TEAMING"})
ALLOWED_STANDARD_TERMS_STATES = frozenset({"ACQUIRED", "LISTED_NOT_ACQUIRED"})
ALLOWED_ADDENDA_STATES = frozenset({"NONE_LISTED", "ALL_LISTED_ACQUIRED", "LISTED_NOT_ACQUIRED"})
OPAQUE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_FIELD = re.compile(r"(?:email|phone|contact|route_address|website|domain|linkedin|url_to_contact)", re.I)

TOP_FIELDS = frozenset({"schema", "evaluated_at_utc", "source_generation", "candidate"})
SOURCE_FIELDS = frozenset(EXPECTED_SOURCE_GENERATION)
CANDIDATE_FIELDS = frozenset({
    "opportunity_ref",
    "route_requested",
    "opportunity_withdrawn",
    "legal_entity_ready",
    "authorized_signer_ready",
    "portal_submission_ready",
    "current_us_reference_count",
    "higher_ed_reference_count",
    "insurance_evidence_ready",
    "similar_cmmc_engagements_evidence_ready",
    "personnel_qualification_evidence_ready",
    "pricing_authority_ready",
    "statutory_certifications_reviewed",
    "partner_prime_identified",
    "partner_prime_responsibility_confirmed",
    "partner_due_diligence_ready",
    "specific_service_scope_agreed",
    "technical_workshare_owner_ready",
    "workshare_price_boundary_ready",
    "cmmc_certification_claimed",
    "external_assessor_authority_claimed",
    "buyer_interest_claimed",
    "award_claimed",
    "revenue_claimed",
    "authorized_cui_environment_ready",
})
BOOL_FIELDS = CANDIDATE_FIELDS - {
    "opportunity_ref", "route_requested", "current_us_reference_count", "higher_ed_reference_count"
}
INT_FIELDS = frozenset({"current_us_reference_count", "higher_ed_reference_count"})
MAX_INPUT_BYTES = 512_000

AUTHORITY = {
    "internal_qualification_only": True,
    "buyer_contact_authorized": False,
    "partner_contact_authorized": False,
    "proposal_submission_authorized": False,
    "portal_mutation_authorized": False,
    "signature_authorized": False,
    "pricing_commitment_authorized": False,
    "contract_acceptance_authorized": False,
    "cmmc_certification_assertion_authorized": False,
    "external_assessment_authority": False,
    "fci_cui_handling_authorized": False,
    "award_inferred": False,
    "revenue_inferred": False,
}

class InputError(ValueError):
    pass

def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise InputError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def _reject_constant(value: str) -> None:
    raise InputError(f"non-finite JSON number: {value}")

def parse_json_strict(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs_no_dupes, parse_constant=_reject_constant)
    except InputError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise InputError(f"invalid JSON: {exc}") from exc

def read_json_file(path: str | os.PathLike[str]) -> Any:
    p = os.fspath(path)
    try:
        before = os.lstat(p)
    except OSError as exc:
        raise InputError(f"input unavailable: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise InputError("input must be an ordinary non-symlink file")
    if before.st_size <= 0 or before.st_size > MAX_INPUT_BYTES:
        raise InputError("input size outside allowed bounds")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise InputError(f"cannot open input safely: {exc}") from exc
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_nlink != 1:
            raise InputError("input must be a single-link regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_INPUT_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise InputError("input exceeds size bound")
            chunks.append(chunk)
        after = os.fstat(fd)
        ident1 = (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns, first.st_ctime_ns)
        ident2 = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if ident1 != ident2 or total != first.st_size:
            raise InputError("input changed during capture")
    finally:
        os.close(fd)
    try:
        return parse_json_strict(b"".join(chunks).decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise InputError("input must be UTF-8") from exc

def _exact_keys(obj: Any, expected: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise InputError(f"{label} must be an object")
    unknown = sorted(set(obj) - expected)
    missing = sorted(expected - set(obj))
    if unknown or missing:
        contactish = [key for key in unknown if FORBIDDEN_FIELD.search(key)]
        if contactish:
            raise InputError(f"{label} contains forbidden contact-route field(s): {contactish}")
        raise InputError(f"{label} schema mismatch: missing={missing}; unknown={unknown}")
    return obj

def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise InputError(f"{name} must be boolean")
    return value

def _int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise InputError(f"{name} must be a nonnegative integer")
    return value

def _utc(value: Any, name: str) -> str:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise InputError(f"{name} must be canonical whole-second UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InputError(f"{name} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise InputError(f"{name} must be UTC")
    return value

def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")

def _normalize_source(value: Any) -> dict[str, Any]:
    obj = _exact_keys(value, SOURCE_FIELDS, "source_generation")
    if obj != EXPECTED_SOURCE_GENERATION:
        raise InputError("source generation drift: refresh HogBid/RFP/addenda before reuse")
    if obj["standard_terms_state"] not in ALLOWED_STANDARD_TERMS_STATES:
        raise InputError("invalid standard_terms_state")
    if obj["addenda_state"] not in ALLOWED_ADDENDA_STATES:
        raise InputError("invalid addenda_state")
    return copy.deepcopy(obj)

def _normalize_candidate(value: Any) -> dict[str, Any]:
    obj = _exact_keys(value, CANDIDATE_FIELDS, "candidate")
    ref = obj["opportunity_ref"]
    if not isinstance(ref, str) or not OPAQUE_REF_RE.fullmatch(ref):
        raise InputError("opportunity_ref must be a bounded opaque reference")
    route = obj["route_requested"]
    if route not in ALLOWED_ROUTES:
        raise InputError("route_requested must be PRIME or TEAMING")
    out: dict[str, Any] = {"opportunity_ref": ref, "route_requested": route}
    for field in sorted(INT_FIELDS):
        out[field] = _int(obj[field], field)
    if out["higher_ed_reference_count"] > out["current_us_reference_count"]:
        raise InputError("higher_ed_reference_count cannot exceed current_us_reference_count")
    for field in sorted(BOOL_FIELDS):
        out[field] = _bool(obj[field], field)
    return out

def _common_blocks(candidate: dict[str, Any], evaluated_at: str, source: dict[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    risks: list[str] = []
    if candidate["opportunity_withdrawn"]:
        blockers.append("OPPORTUNITY_WITHDRAWN")
    if _dt(evaluated_at) >= _dt(PROPOSAL_DEADLINE_UTC):
        blockers.append("PROPOSAL_DEADLINE_PASSED")
    if not source["rfp_content_acquired"]:
        blockers.append("CONTROLLING_RFP_NOT_ACQUIRED")
    if source["addenda_state"] == "LISTED_NOT_ACQUIRED":
        blockers.append("LISTED_ADDENDA_NOT_ACQUIRED")
    if candidate["cmmc_certification_claimed"]:
        blockers.append("UNAUTHORIZED_CMMC_CERTIFICATION_CLAIM")
    if candidate["external_assessor_authority_claimed"]:
        blockers.append("UNAUTHORIZED_EXTERNAL_ASSESSOR_CLAIM")
    if candidate["buyer_interest_claimed"]:
        blockers.append("BUYER_INTEREST_CLAIM_PRESENT")
    if candidate["award_claimed"]:
        blockers.append("AWARD_CLAIM_PRESENT")
    if candidate["revenue_claimed"]:
        blockers.append("REVENUE_CLAIM_PRESENT")
    if candidate["authorized_cui_environment_ready"]:
        risks.append("AUTHORIZED_CUI_ENVIRONMENT_REPORTED_BUT_THIS_CARRIER_STILL_DOES_NOT_AUTHORIZE_CUI_HANDLING")
    if source["standard_terms_state"] != "ACQUIRED":
        risks.append("STANDARD_TERMS_LISTED_NOT_ACQUIRED")
    if source["addenda_state"] == "NONE_LISTED":
        risks.append("ADDENDA_MAY_STILL_ISSUE_THROUGH_2026_10_05_RECHECK_REQUIRED")
    if _dt(evaluated_at) >= _dt(QUESTION_DEADLINE_UTC):
        risks.append("QUESTION_DEADLINE_PASSED")
    return blockers, risks

def _prime_blocks(candidate: dict[str, Any], source: dict[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    risks: list[str] = []
    if source["standard_terms_state"] != "ACQUIRED":
        blockers.append("STANDARD_TERMS_NOT_ACQUIRED_FOR_SUBMISSION")
    required_true = (
        ("legal_entity_ready", "LEGAL_ENTITY_NOT_READY"),
        ("authorized_signer_ready", "AUTHORIZED_SIGNER_NOT_READY"),
        ("portal_submission_ready", "PORTAL_SUBMISSION_NOT_READY"),
        ("insurance_evidence_ready", "INSURANCE_EVIDENCE_NOT_READY"),
        ("similar_cmmc_engagements_evidence_ready", "SIMILAR_CMMC_ENGAGEMENT_EVIDENCE_NOT_READY"),
        ("personnel_qualification_evidence_ready", "PERSONNEL_QUALIFICATION_EVIDENCE_NOT_READY"),
        ("pricing_authority_ready", "PRICING_AUTHORITY_NOT_READY"),
        ("statutory_certifications_reviewed", "STATUTORY_CERTIFICATIONS_NOT_REVIEWED"),
    )
    for field, reason in required_true:
        if not candidate[field]:
            blockers.append(reason)
    if candidate["current_us_reference_count"] < 3:
        blockers.append("MINIMUM_THREE_CURRENT_US_REFERENCES_NOT_MET")
    if candidate["higher_ed_reference_count"] == 0:
        risks.append("QUALIFICATION_SCORE_RISK_NO_HIGHER_ED_REFERENCE")
    elif candidate["higher_ed_reference_count"] < 3:
        risks.append("QUALIFICATION_SCORE_RISK_FEWER_THAN_THREE_HIGHER_ED_REFERENCES")
    return blockers, risks

def _teaming_blocks(candidate: dict[str, Any]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    risks: list[str] = []
    required_true = (
        ("partner_prime_identified", "PARTNER_PRIME_NOT_IDENTIFIED"),
        ("partner_prime_responsibility_confirmed", "PARTNER_PRIME_RESPONSIBILITY_NOT_CONFIRMED"),
        ("partner_due_diligence_ready", "PARTNER_DUE_DILIGENCE_NOT_READY"),
        ("specific_service_scope_agreed", "SPECIFIC_SERVICE_SCOPE_NOT_AGREED"),
        ("technical_workshare_owner_ready", "TECHNICAL_WORKSHARE_OWNER_NOT_READY"),
        ("workshare_price_boundary_ready", "WORKSHARE_PRICE_BOUNDARY_NOT_READY"),
    )
    for field, reason in required_true:
        if not candidate[field]:
            blockers.append(reason)
    if not candidate["personnel_qualification_evidence_ready"]:
        blockers.append("WORKSHARE_PERSONNEL_EVIDENCE_NOT_READY")
    if not candidate["similar_cmmc_engagements_evidence_ready"]:
        risks.append("PARTNER_MUST_CARRY_PROGRAM_LEVEL_SIMILAR_ENGAGEMENT_CREDIBILITY")
    if candidate["current_us_reference_count"] < 3:
        risks.append("OUR_DIRECT_PRIME_REFERENCE_GATE_NOT_MET_PARTNER_MUST_CARRY")
    if not candidate["insurance_evidence_ready"]:
        risks.append("OUR_DIRECT_PRIME_INSURANCE_GATE_NOT_MET_PARTNER_MUST_CARRY_OR_ALLOCATE")
    return blockers, risks

def compile_qualification(intake: Any) -> dict[str, Any]:
    obj = _exact_keys(intake, TOP_FIELDS, "intake")
    if obj["schema"] != SCHEMA:
        raise InputError("unsupported schema")
    evaluated_at = _utc(obj["evaluated_at_utc"], "evaluated_at_utc")
    source = _normalize_source(obj["source_generation"])
    candidate = _normalize_candidate(obj["candidate"])

    common, risks = _common_blocks(candidate, evaluated_at, source)
    if "OPPORTUNITY_WITHDRAWN" in common or "PROPOSAL_DEADLINE_PASSED" in common:
        status = "NO_BID"
        blockers = common
    else:
        if candidate["route_requested"] == "PRIME":
            route_blocks, route_risks = _prime_blocks(candidate, source)
            status = "PRIME_READY" if not common and not route_blocks else "HOLD"
        else:
            route_blocks, route_risks = _teaming_blocks(candidate)
            status = "TEAMING_READY" if not common and not route_blocks else "HOLD"
        blockers = common + route_blocks
        risks += route_risks

    decision = {
        "opportunity_ref": candidate["opportunity_ref"],
        "route_requested": candidate["route_requested"],
        "status": status,
        "blockers": blockers,
        "risks": sorted(set(risks)),
        "submission_ready": status == "PRIME_READY" and source["standard_terms_state"] == "ACQUIRED",
        "partner_outreach_authorized": False,
        "authority": copy.deepcopy(AUTHORITY),
    }
    decision["decision_receipt_sha256"] = sha256_obj(decision)
    packet = {
        "schema": PACKET_SCHEMA,
        "operation": OPERATION,
        "owner": OWNER,
        "model": MODEL,
        "evaluated_at_utc": evaluated_at,
        "buyer": "University of Arkansas Fayetteville",
        "rfp_number": RFP_NUMBER,
        "question_deadline_utc": QUESTION_DEADLINE_UTC,
        "proposal_deadline_utc": PROPOSAL_DEADLINE_UTC,
        "last_planned_addendum_date": LAST_PLANNED_ADDENDUM_DATE,
        "internal_workshare_target_usd": INTERNAL_WORKSHARE_TARGET_USD,
        "price_boundary": PRICE_BOUNDARY,
        "source_generation": source,
        "candidate": candidate,
        "decision": decision,
    }
    packet["packet_receipt_sha256"] = sha256_obj(packet)
    return packet

def verify_packet(packet: Any) -> bool:
    required = {
        "schema", "operation", "owner", "model", "evaluated_at_utc", "buyer",
        "rfp_number", "question_deadline_utc", "proposal_deadline_utc",
        "last_planned_addendum_date", "internal_workshare_target_usd",
        "price_boundary", "source_generation", "candidate", "decision",
        "packet_receipt_sha256",
    }
    if not isinstance(packet, dict) or set(packet) != required:
        raise InputError("packet schema mismatch")
    receipt = packet["packet_receipt_sha256"]
    if not isinstance(receipt, str) or not SHA_RE.fullmatch(receipt):
        raise InputError("packet receipt invalid")
    unsigned = copy.deepcopy(packet)
    unsigned.pop("packet_receipt_sha256")
    if sha256_obj(unsigned) != receipt:
        raise InputError("packet receipt mismatch")
    source_intake = {
        "schema": SCHEMA,
        "evaluated_at_utc": packet["evaluated_at_utc"],
        "source_generation": packet["source_generation"],
        "candidate": packet["candidate"],
    }
    expected = compile_qualification(source_intake)
    if packet != expected:
        raise InputError("packet semantic verification failed")
    return True

def render_markdown(packet: dict[str, Any]) -> str:
    verify_packet(packet)
    d = packet["decision"]
    blockers = "\n".join(f"- {x}" for x in d["blockers"]) or "- none"
    risks = "\n".join(f"- {x}" for x in d["risks"]) or "- none"
    return (
        "# UArk RFP09112026 qualification\n\n"
        f"**Route:** `{d['route_requested']}`  \n"
        f"**Status:** `{d['status']}`  \n"
        f"**Submission ready:** `{str(d['submission_ready']).lower()}`  \n"
        f"**Internal workshare target:** `${packet['internal_workshare_target_usd']:,}` — `{PRICE_BOUNDARY}`\n\n"
        "## Blockers\n" + blockers + "\n\n"
        "## Risks / packet gaps\n" + risks + "\n\n"
        "## Authority boundary\n"
        "This result authorizes no buyer or partner contact, no portal action, no signature, no price commitment, "
        "no certification/assessment representation, no FCI/CUI handling, no contract acceptance, and no award/revenue claim. "
        "Any email requires a fresh collision/provider-history fence and explicit Muse single-writer selection.\n\n"
        f"Receipt: `{packet['packet_receipt_sha256']}`\n"
    )

def _write_exclusive(path: str, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise InputError(f"output unavailable for exclusive create: {exc}") from exc
    try:
        data = text.encode("utf-8")
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise InputError("short output write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Qualify UArk RFP09112026 PRIME/TEAMING route without outbound authority")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("input_json")
    c.add_argument("--json-out")
    c.add_argument("--markdown-out")
    v = sub.add_parser("verify")
    v.add_argument("packet_json")
    return p

def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "compile":
            packet = compile_qualification(read_json_file(args.input_json))
            json_text = canonical_json(packet) + "\n"
            md_text = render_markdown(packet)
            if args.json_out:
                _write_exclusive(args.json_out, json_text)
            else:
                sys.stdout.write(json_text)
            if args.markdown_out:
                _write_exclusive(args.markdown_out, md_text)
            return 0
        if args.command == "verify":
            verify_packet(read_json_file(args.packet_json))
            print("VERIFIED")
            return 0
        raise InputError("unknown command")
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
