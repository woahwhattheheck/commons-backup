"""Deterministic Water4All 2026 consortium-readiness compiler."""

from __future__ import annotations

import copy
import datetime as _dt
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .common import (
    BUNDLE_SCHEMA,
    CURRENT_PACKET_MAX_AGE_SECONDS,
    FUTURE_SKEW_SECONDS,
    INPUT_SCHEMA,
    PACKET_SCHEMA,
    ReadinessError,
    _assert_json_value,
    _expect_dict,
    _expect_str,
    canonical_bytes,
    format_time,
    parse_time,
    seal_source,
    sha256_hex,
    source_fact_commitment,
    strict_json_loads,
    utc_now,
)
from .consortium_validation import _validate_applicant, _validate_consortium
from .evidence_validation import _validate_commercial, _validate_concept_and_evidence, _validate_partner_shortlist
from .source_validation import _validate_sources


def _hold_status_from_reasons(groups: Mapping[str, Sequence[Dict[str, Any]]]) -> str:
    if groups["source"]:
        if any(reason["code"] == "DEADLINE_SOURCE_CONFLICT" for reason in groups["source"]):
            return "HOLD_DEADLINE_SOURCE_CONFLICT"
        return "HOLD_SOURCE_AUTHORITY"
    if groups["consortium"]:
        return "HOLD_CONSORTIUM"
    if groups["applicant"]:
        return "HOLD_APPLICANT_ROLE"
    if groups["technical"]:
        return "HOLD_TECHNICAL_EVIDENCE"
    if groups["partner_shortlist"]:
        return "HOLD_PARTNER_RESEARCH"
    if groups["commercial"]:
        return "HOLD_COMMERCIAL_AUTHORITY"
    return "HISTORICAL_INTEGRITY_ONLY"


def _current_status_from_reasons(
    groups: Mapping[str, Sequence[Dict[str, Any]]],
    authority_root: Any,
) -> str:
    held = _hold_status_from_reasons(groups)
    if held != "HISTORICAL_INTEGRITY_ONLY":
        return held
    if authority_root:
        return "READY_FOR_OWNER_REVIEW"
    return "HISTORICAL_INTEGRITY_ONLY"


def _semantic_projection(packet: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "source_generation_sha256": packet["source_generation_sha256"],
        "input_sha256": packet["input_sha256"],
        "decision": packet["decision"],
        "consortium": packet["consortium"],
        "applicant": packet["applicant"],
        "concept_and_evidence": packet["concept_and_evidence"],
        "commercial": packet["commercial"],
        "authority": packet["authority"],
    }


def _collect_input_facts(input_value: Any, evaluated_at: _dt.datetime, current_mode: bool) -> Dict[str, Any]:
    if evaluated_at.tzinfo is None:
        raise ReadinessError("evaluation time must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(_dt.timezone.utc).replace(microsecond=0)
    root = _expect_dict(copy.deepcopy(input_value), "$")
    _assert_json_value(root)
    if root.get("schema") != INPUT_SCHEMA:
        raise ReadinessError("unsupported input schema")

    sources, source_reasons, controlling_deadline, planning_deadline, source_generation = _validate_sources(
        root.get("official_sources"), evaluated_at, current_mode
    )
    consortium, consortium_reasons, consortium_by_id = _validate_consortium(root.get("consortium"))
    applicant, applicant_reasons = _validate_applicant(root.get("applicant"), consortium_by_id)
    concept_and_evidence, technical_reasons = _validate_concept_and_evidence(
        root.get("concept"), root.get("technical_evidence"), evaluated_at, current_mode
    )
    partner_shortlist, partner_reasons = _validate_partner_shortlist(root.get("partner_shortlist"))
    commercial, commercial_reasons = _validate_commercial(root.get("commercial"))
    groups: Dict[str, List[Dict[str, Any]]] = {
        "source": source_reasons,
        "consortium": consortium_reasons,
        "applicant": applicant_reasons,
        "technical": technical_reasons,
        "partner_shortlist": partner_reasons,
        "commercial": commercial_reasons,
    }
    for value in groups.values():
        value.sort(key=lambda item: (item["code"], item["detail"], item["refs"]))
    all_reasons: List[Dict[str, Any]] = []
    for group_name in ("source", "consortium", "applicant", "technical", "partner_shortlist", "commercial"):
        for item in groups[group_name]:
            enriched = dict(item)
            enriched["group"] = group_name
            all_reasons.append(enriched)
    return {
        "evaluated_at": evaluated_at,
        "root": root,
        "sources": sources,
        "controlling_deadline": controlling_deadline,
        "planning_deadline": planning_deadline,
        "source_generation": source_generation,
        "consortium": consortium,
        "applicant": applicant,
        "concept_and_evidence": concept_and_evidence,
        "partner_shortlist": partner_shortlist,
        "commercial": commercial,
        "groups": groups,
        "all_reasons": all_reasons,
    }


def _bundle_from_evaluation(evaluation: Mapping[str, Any], mode: str, status: str) -> Dict[str, Any]:
    packet: Dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "mode": mode,
        "generated_at": format_time(evaluation["evaluated_at"]),
        "input_sha256": sha256_hex(evaluation["root"]),
        "source_generation_sha256": evaluation["source_generation"],
        "official_sources": evaluation["sources"],
        "deadline_authority": {
            "controlling_preproposal_deadline_at": evaluation["controlling_deadline"],
            "planning_only_earliest_deadline_at": evaluation["planning_deadline"],
            "planning_only": evaluation["controlling_deadline"] is None,
        },
        "consortium": evaluation["consortium"],
        "applicant": evaluation["applicant"],
        "concept_and_evidence": evaluation["concept_and_evidence"],
        "partner_shortlist": evaluation["partner_shortlist"],
        "commercial": evaluation["commercial"],
        "decision": {
            "status": status,
            "reason_count": len(evaluation["all_reasons"]),
            "reasons": evaluation["all_reasons"],
        },
        "authority": {
            "integrity_receipt_is_signature": False,
            "external_contact_authorized": False,
            "portal_or_pic_action_authorized": False,
            "consortium_commitment_authorized": False,
            "self_funding_committed": False,
            "price_quote_authorized": False,
            "submission_authorized": False,
            "spend_authorized": False,
            "award_claimed": False,
            "payment_claimed": False,
            "revenue_recognized": False,
        },
    }
    packet["semantic_sha256"] = sha256_hex(_semantic_projection(packet))
    return {
        "schema": BUNDLE_SCHEMA,
        "packet": packet,
        "receipt": {
            "algorithm": "SHA-256-INTEGRITY-ONLY",
            "packet_sha256": sha256_hex(packet),
            "signature": False,
        },
    }


def _compile_historical_at(input_value: Any, evaluated_at: _dt.datetime) -> Dict[str, Any]:
    evaluation = _collect_input_facts(input_value, evaluated_at, False)
    return _bundle_from_evaluation(evaluation, "HISTORICAL", _hold_status_from_reasons(evaluation["groups"]))


def _compile_current_at(input_value: Any, evaluated_at: _dt.datetime, authority_root: Any) -> Dict[str, Any]:
    evaluation = _collect_input_facts(input_value, evaluated_at, True)
    return _bundle_from_evaluation(
        evaluation,
        "CURRENT",
        _current_status_from_reasons(evaluation["groups"], authority_root),
    )


def compile_at(input_value: Any, evaluated_at: _dt.datetime, mode: str) -> Dict[str, Any]:
    """Compile a HISTORICAL readiness bundle at an explicit retained time.

    CURRENT compilation is not available here. Callers that need live time
    must use compile_current, which samples process UTC and consumes an
    independent authority_root. Historical compilation never mints
    READY_FOR_OWNER_REVIEW.
    """
    if mode == "CURRENT":
        raise ReadinessError("compile_at cannot mint CURRENT packets; use compile_current")
    if mode != "HISTORICAL":
        raise ReadinessError("mode must be CURRENT or HISTORICAL")
    return _compile_historical_at(input_value, evaluated_at)


def compile_historical(input_value: Any, evaluated_at: Any) -> Dict[str, Any]:
    when = parse_time(evaluated_at, "evaluated_at") if not isinstance(evaluated_at, _dt.datetime) else evaluated_at
    return _compile_historical_at(input_value, when)


def compile_current(input_value: Any, authority_root: Any) -> Dict[str, Any]:
    if not authority_root:
        raise ReadinessError("independent authority is required")
    return _compile_current_at(input_value, utc_now(), authority_root)


def verify_bundle(input_value: Any, bundle_value: Any, authority_root: Any) -> Dict[str, Any]:
    """Verify integrity and live CURRENT semantics.

    Caller time is not authority for CURRENT packets. The verifier samples
    process UTC itself. An independent authority_root is the controlling
    condition on every current-accepting path.
    """
    if not authority_root:
        raise ReadinessError("independent authority is required")
    bundle = _expect_dict(copy.deepcopy(bundle_value), "bundle")
    if bundle.get("schema") != BUNDLE_SCHEMA:
        raise ReadinessError("unsupported bundle schema")
    packet = _expect_dict(bundle.get("packet"), "bundle.packet")
    receipt = _expect_dict(bundle.get("receipt"), "bundle.receipt")
    if packet.get("schema") != PACKET_SCHEMA:
        raise ReadinessError("unsupported packet schema")
    if receipt.get("algorithm") != "SHA-256-INTEGRITY-ONLY" or receipt.get("signature") is not False:
        raise ReadinessError("unsupported or misleading receipt")
    expected_packet_hash = sha256_hex(packet)
    if receipt.get("packet_sha256") != expected_packet_hash:
        raise ReadinessError("packet integrity receipt mismatch")

    mode = _expect_str(packet.get("mode"), "bundle.packet.mode")
    generated_at = parse_time(packet.get("generated_at"), "bundle.packet.generated_at")
    if mode == "CURRENT":
        exact = _compile_current_at(input_value, generated_at, authority_root)
    elif mode == "HISTORICAL":
        exact = _compile_historical_at(input_value, generated_at)
    else:
        raise ReadinessError("mode must be CURRENT or HISTORICAL")
    if canonical_bytes(exact) != canonical_bytes(bundle):
        raise ReadinessError("bundle does not exactly replay from input at retained generation")

    result = {
        "valid": True,
        "mode": mode,
        "current_semantics": False,
        "status": packet["decision"]["status"],
        "packet_sha256": expected_packet_hash,
    }
    if mode == "CURRENT":
        now = utc_now()
        if generated_at > now + _dt.timedelta(seconds=FUTURE_SKEW_SECONDS):
            raise ReadinessError("current packet was generated in the future")
        if now - generated_at > _dt.timedelta(seconds=CURRENT_PACKET_MAX_AGE_SECONDS):
            raise ReadinessError("current packet exceeds verifier freshness window")
        live = _compile_current_at(input_value, now, authority_root)
        if live["packet"]["semantic_sha256"] != packet.get("semantic_sha256"):
            raise ReadinessError("current semantics drifted since packet generation")
        result["current_semantics"] = True
    else:
        result["historical_integrity_only"] = True
    return result


def render_owner_markdown(bundle_value: Any) -> str:
    bundle = _expect_dict(bundle_value, "bundle")
    packet = _expect_dict(bundle.get("packet"), "bundle.packet")
    decision = _expect_dict(packet.get("decision"), "bundle.packet.decision")
    lines = [
        "# Water4All 2026 Sustainable Water Management — Owner Review",
        "",
        "- Status: `%s`" % decision.get("status"),
        "- Mode: `%s`" % packet.get("mode"),
        "- Generated: `%s`" % packet.get("generated_at"),
        "- Controlling pre-proposal deadline: `%s`" % (packet["deadline_authority"].get("controlling_preproposal_deadline_at") or "UNRESOLVED"),
        "- Planning-only earliest deadline: `%s`" % (packet["deadline_authority"].get("planning_only_earliest_deadline_at") or "UNKNOWN"),
        "- External contact authorized: `false`",
        "- Submission authorized: `false`",
        "- Revenue recognized: `false`",
        "",
        "## Holds",
    ]
    reasons = decision.get("reasons", [])
    if not reasons:
        lines.append("- No compiler hold. Human owner review is still required.")
    else:
        for reason in reasons:
            code = str(reason.get("code", "UNKNOWN")).replace("`", "&#96;")
            detail = str(reason.get("detail", "")).replace("\r", " ").replace("\n", " ").replace("`", "&#96;")
            lines.append("- `%s`: %s" % (code, detail))
    lines.extend(["", "> Integrity receipts are not signatures. This packet cannot contact a partner, commit funding, quote a price, or submit a proposal.", ""])
    return "\n".join(lines)
