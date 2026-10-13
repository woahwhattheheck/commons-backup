#!/usr/bin/env python3
"""Deterministic CPCA HCCN Connect partner-workshare compiler.

This package helps scope a bounded AI subcontract with a healthcare-qualified
prime. It never authorizes contact, CPCA submission, credential use, pricing,
contracting, award/payment claims, or revenue recognition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "cpca-hccn-partner-workshare/v1"
RESULT_SCHEMA = "cpca-hccn-partner-workshare-result/v1"
OPPORTUNITY_ID = "CPCA-HCCN-CONNECT-RFP-1-2026"

AI_TOPICS = (
    "AI Governance",
    "AI Vendor Evaluation",
    "AI Use Case Education",
    "AI Implementation",
)
SERVICE_TYPES = ("technical_assistance", "group_training")
RELATIONSHIP_STATES = (
    "UNCONTACTED",
    "AWAITING_REPLY",
    "POSITIVE_INTEREST",
    "WRITTEN_TEAMING_AUTHORITY",
)
EVIDENCE_STATES = ("UNKNOWN", "SOURCE_BOUND", "NOT_AVAILABLE")
PARTNER_GATES = (
    "safety_net_comparable_engagement",
    "three_client_references",
    "named_personnel_and_resumes",
    "licensing_insurance_accreditation",
    "cultural_competency",
    "delivery_capacity",
    "regulatory_standards_knowledge",
)
TJL_SCOPES = (
    "ai_governance_risk_control_matrix",
    "ai_vendor_evaluation_rubric",
    "ai_use_case_readiness_matrix",
    "ai_implementation_assurance",
    "deterministic_evaluation_test_evidence",
    "technical_handoff_and_work_products",
)
TJL_EVIDENCE = ("ai_subject_matter_evidence", "technical_work_sample")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class WorkshareError(ValueError):
    pass


def strict_load(path: Path) -> Any:
    def hook(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise WorkshareError(f"duplicate JSON key: {k}")
            out[k] = v
        return out

    def bad_constant(v):
        raise WorkshareError(f"non-finite JSON constant: {v}")

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=hook,
            parse_constant=bad_constant,
        )
    except json.JSONDecodeError as exc:
        raise WorkshareError(f"invalid JSON: {exc}") from exc


def exact_object(value: Any, where: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise WorkshareError(f"{where} must be an object")
    extra = sorted(set(value) - keys)
    missing = sorted(keys - set(value))
    if extra:
        raise WorkshareError(f"{where} unknown keys: {extra}")
    if missing:
        raise WorkshareError(f"{where} missing keys: {missing}")
    return value


def text(value: Any, where: str, max_len: int = 240) -> str:
    if type(value) is not str:
        raise WorkshareError(f"{where} must be a string")
    value = value.strip()
    if not value or len(value) > max_len or "\x00" in value:
        raise WorkshareError(f"{where} must be non-empty and <= {max_len} chars")
    return value


def enum(value: Any, where: str, allowed: tuple[str, ...]) -> str:
    value = text(value, where)
    if value not in allowed:
        raise WorkshareError(f"{where} must be one of {list(allowed)}")
    return value


def enum_list(value: Any, where: str, allowed: tuple[str, ...]) -> list[str]:
    if type(value) is not list or not value:
        raise WorkshareError(f"{where} must be a non-empty array")
    out = []
    for i, item in enumerate(value):
        item = enum(item, f"{where}[{i}]", allowed)
        if item in out:
            raise WorkshareError(f"{where} contains duplicate {item!r}")
        out.append(item)
    return sorted(out)


def evidence(value: Any, where: str) -> dict[str, str]:
    value = exact_object(value, where, {"state", "source_ref", "sha256"})
    state = enum(value["state"], f"{where}.state", EVIDENCE_STATES)
    if type(value["source_ref"]) is not str or type(value["sha256"]) is not str:
        raise WorkshareError(f"{where}.source_ref and sha256 must be strings")
    ref = value["source_ref"].strip()
    digest_value = value["sha256"].strip()
    if state == "SOURCE_BOUND":
        if not ref or len(ref) > 300:
            raise WorkshareError(f"{where}.source_ref required when SOURCE_BOUND")
        if not HEX64.fullmatch(digest_value):
            raise WorkshareError(
                f"{where}.sha256 must be lowercase 64-hex when SOURCE_BOUND"
            )
    elif ref or digest_value:
        raise WorkshareError(
            f"{where} may carry source_ref/sha256 only when SOURCE_BOUND"
        )
    return {"state": state, "source_ref": ref, "sha256": digest_value}


def normalize(raw: Any) -> dict[str, Any]:
    raw = exact_object(
        raw,
        "root",
        {
            "schema",
            "opportunity_id",
            "candidate_partner",
            "service_types",
            "ai_topics",
            "tjlabs_scope",
            "partner_gate_evidence",
            "tjlabs_evidence",
        },
    )
    if text(raw["schema"], "schema") != SCHEMA:
        raise WorkshareError(f"schema must equal {SCHEMA}")
    if text(raw["opportunity_id"], "opportunity_id") != OPPORTUNITY_ID:
        raise WorkshareError(f"opportunity_id must equal {OPPORTUNITY_ID}")

    partner = exact_object(
        raw["candidate_partner"],
        "candidate_partner",
        {"name", "applicant_role", "relationship_state", "relationship_evidence"},
    )
    name = text(partner["name"], "candidate_partner.name", 160)
    role = enum(partner["applicant_role"], "candidate_partner.applicant_role", ("PRIME",))
    rel_state = enum(
        partner["relationship_state"],
        "candidate_partner.relationship_state",
        RELATIONSHIP_STATES,
    )
    rel_ev = evidence(
        partner["relationship_evidence"],
        "candidate_partner.relationship_evidence",
    )
    if rel_state == "WRITTEN_TEAMING_AUTHORITY" and rel_ev["state"] != "SOURCE_BOUND":
        raise WorkshareError(
            "WRITTEN_TEAMING_AUTHORITY requires SOURCE_BOUND relationship evidence"
        )

    pg = exact_object(
        raw["partner_gate_evidence"], "partner_gate_evidence", set(PARTNER_GATES)
    )
    te = exact_object(raw["tjlabs_evidence"], "tjlabs_evidence", set(TJL_EVIDENCE))

    return {
        "schema": SCHEMA,
        "opportunity_id": OPPORTUNITY_ID,
        "candidate_partner": {
            "name": name,
            "applicant_role": role,
            "relationship_state": rel_state,
            "relationship_evidence": rel_ev,
        },
        "service_types": enum_list(raw["service_types"], "service_types", SERVICE_TYPES),
        "ai_topics": enum_list(raw["ai_topics"], "ai_topics", AI_TOPICS),
        "tjlabs_scope": enum_list(raw["tjlabs_scope"], "tjlabs_scope", TJL_SCOPES),
        "partner_gate_evidence": {
            k: evidence(pg[k], f"partner_gate_evidence.{k}") for k in PARTNER_GATES
        },
        "tjlabs_evidence": {
            k: evidence(te[k], f"tjlabs_evidence.{k}") for k in TJL_EVIDENCE
        },
    }


def digest(obj: Any) -> str:
    data = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compile_packet(raw: Any) -> dict[str, Any]:
    packet = normalize(raw)
    rel = packet["candidate_partner"]["relationship_state"]
    missing_partner = sorted(
        k
        for k, v in packet["partner_gate_evidence"].items()
        if v["state"] != "SOURCE_BOUND"
    )
    missing_tjl = sorted(
        k
        for k, v in packet["tjlabs_evidence"].items()
        if v["state"] != "SOURCE_BOUND"
    )

    reasons: list[str] = []
    if rel in ("UNCONTACTED", "AWAITING_REPLY"):
        status = "DRAFT_ONLY"
        reasons.append("NO_POSITIVE_PARTNER_EVENT")
    elif rel == "POSITIVE_INTEREST":
        status = "PARTNER_DISCUSSION_READY"
        reasons.append("POSITIVE_INTEREST_NOT_WRITTEN_TEAMING_AUTHORITY")
    elif missing_partner or missing_tjl:
        status = "HOLD_EVIDENCE"
    else:
        status = "INTERNAL_TEAMING_REVIEW_READY"

    reasons += [f"PARTNER_GATE_UNBOUND:{k}" for k in missing_partner]
    reasons += [f"TJLABS_EVIDENCE_UNBOUND:{k}" for k in missing_tjl]

    result = {
        "schema": RESULT_SCHEMA,
        "opportunity_id": OPPORTUNITY_ID,
        "candidate_partner": packet["candidate_partner"]["name"],
        "status": status,
        "reasons": sorted(reasons),
        "selected_service_types": packet["service_types"],
        "selected_ai_topics": packet["ai_topics"],
        "tjlabs_scope": packet["tjlabs_scope"],
        "responsibility_split": {
            "qualified_prime_owns": [
                "CPCA applicant identity and SmartSheet submission",
                "FQHC/safety-net comparable-engagement claims",
                "client references and permission to use them",
                "named personnel/resumes and healthcare/domain credentials",
                "licensing, insurance, accreditation, and legal attestations",
                "rate sheet and commercial terms submitted to CPCA",
                "CPCA Engagement Agreement/BAA and invoicing/reporting",
            ],
            "tjlabs_owns_only_if_separately_supported": [
                "AI governance risk/control design",
                "AI vendor evaluation and evidence rubric",
                "AI use-case readiness and acceptance criteria",
                "AI implementation assurance and deterministic test/evidence design",
                "technical work products and handoff artifacts",
            ],
            "joint_after_written_authority": [
                "project-specific SOW, milestones, deliverables, and acceptance evidence",
                "division of labor for Technical Assistance and/or Group Training",
                "customer-safe escalation, change control, and final handoff",
            ],
        },
        "authority_ceiling": {
            "external_contact_authorized": False,
            "external_submission_authorized": False,
            "partner_credential_use_authorized": False,
            "price_commitment_authorized": False,
            "contract_authorized": False,
            "award_or_payment_claim_authorized": False,
            "revenue_recognition_authorized": False,
        },
        "normalized_input_sha256": digest(packet),
    }
    result["receipt_sha256"] = digest(result)
    return result


def verify(raw: Any, result: Mapping[str, Any]) -> bool:
    return type(result) is dict and result == compile_packet(raw)


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# CPCA HCCN Connect — AI-domain partner workshare",
        "",
        f"**Candidate healthcare prime:** {result['candidate_partner']}  ",
        f"**Internal state:** `{result['status']}`  ",
        f"**CPCA AI topics:** {', '.join(result['selected_ai_topics'])}  ",
        f"**Service types:** {', '.join(result['selected_service_types'])}",
        "",
        "## Division of responsibility",
        "",
        "**Qualified healthcare prime owns**",
    ]
    lines += [f"- {x}" for x in result["responsibility_split"]["qualified_prime_owns"]]
    lines += ["", "**Token Junkie Labs support scope — only where separately evidenced**"]
    lines += [
        f"- {x}"
        for x in result["responsibility_split"][
            "tjlabs_owns_only_if_separately_supported"
        ]
    ]
    lines += ["", "**Joint only after written teaming authority**"]
    lines += [
        f"- {x}"
        for x in result["responsibility_split"]["joint_after_written_authority"]
    ]
    lines += ["", "## Evidence still required before internal teaming review", ""]
    if result["reasons"]:
        lines += [f"- `{x}`" for x in result["reasons"]]
    else:
        lines += ["- None at this compiler layer; run the canonical CPCA qualification gate next."]
    lines += [
        "",
        "## Commercial / authority boundary",
        "",
        "This packet is a division-of-responsibility aid. It does **not** make the candidate a partner,",
        "authorize use of the candidate's credentials or references, set CPCA or subcontract pricing,",
        "authorize buyer/partner contact or SmartSheet submission, create a contract, or establish an",
        "award, payment, cash receipt, or recognized revenue. The canonical CPCA qualification carrier",
        "and human/provider authority remain controlling.",
        "",
        f"`receipt_sha256={result['receipt_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile")
    c.add_argument("input")
    c.add_argument("--json-out")
    c.add_argument("--md-out")

    v = sub.add_parser("verify")
    v.add_argument("input")
    v.add_argument("result")

    args = parser.parse_args(argv)
    if args.cmd == "compile":
        result = compile_packet(strict_load(Path(args.input)))
        js = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        md = render_markdown(result)
        if args.json_out:
            Path(args.json_out).write_text(js, encoding="utf-8")
        else:
            print(js, end="")
        if args.md_out:
            Path(args.md_out).write_text(md, encoding="utf-8")
        return 0

    ok = verify(strict_load(Path(args.input)), strict_load(Path(args.result)))
    print("VALID" if ok else "INVALID")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
