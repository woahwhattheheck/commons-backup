from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parent
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")
_QUESTIONS = datetime.fromisoformat("2026-09-21T15:30:00-04:00")
_DEADLINE = datetime.fromisoformat("2026-10-09T14:30:00-04:00")

_EXPECTED_TOP = {
    "source_manifest_digest",
    "evaluated_at",
    "controlling_package",
    "qualification",
    "commercial",
    "submission",
}
_EXPECTED_PACKAGE = {
    "acquired",
    "sha256",
    "addenda_complete",
    "requirement_register_bound",
}
_EXPECTED_QUALIFICATION = {
    "entity_eligibility_evidence_digest",
    "insurance_evidence_digest",
    "references_evidence_digest",
    "housing_authority_experience_evidence_digest",
    "conflict_disclosure",
}
_EXPECTED_COMMERCIAL = {
    "currency",
    "price_minor",
    "owner_price_confirmed",
    "structure_matches_controlling_package",
}
_EXPECTED_SUBMISSION = {
    "channel",
    "portal_account_verified",
    "forms_complete",
    "owner_ruling",
    "fresh_portal_state_observed",
}
_AUTHORITY_FALSE = {
    "buyer_contact_authorized": False,
    "portal_registration_authorized": False,
    "clarification_authorized": False,
    "submission_authorized": False,
    "signature_authorized": False,
    "pricing_commitment_authorized": False,
    "credential_invention_authorized": False,
    "contract_acceptance_authorized": False,
    "award_claimed": False,
    "payment_claimed": False,
    "revenue_claimed": False,
}


class CarrierError(ValueError):
    pass


def _strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise CarrierError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text):
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CarrierError(f"non-finite JSON number: {token}")
            ),
        )
    except CarrierError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise CarrierError(f"invalid JSON: {exc}") from exc


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load_manifest():
    manifest = loads_strict((_ROOT / "source_manifest.json").read_text(encoding="utf-8"))
    if type(manifest) is not dict:
        raise CarrierError("source manifest must be an object")
    return manifest


_SOURCE = _load_manifest()
_SOURCE_DIGEST = _digest(_SOURCE)
_BUYER = deepcopy(_SOURCE["buyer_facts"])


def source_manifest_digest():
    return _SOURCE_DIGEST


def _exact_object(value, keys, label):
    if type(value) is not dict:
        raise CarrierError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise CarrierError(f"{label} keys mismatch missing={missing} extra={extra}")
    return value


def _sha_or_none(value, label):
    if value is None:
        return None
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise CarrierError(f"{label} must be null or lowercase sha256")
    return value


def _strict_bool(value, label):
    if type(value) is not bool:
        raise CarrierError(f"{label} must be boolean")
    return value


def _strict_int(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise CarrierError(f"{label} must be integer >= {minimum}")
    return value


def _evaluation_time(value):
    if type(value) is not str:
        raise CarrierError("evaluated_at must be an ISO timestamp string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CarrierError("evaluated_at is not valid ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CarrierError("evaluated_at must include an offset")
    return parsed


def _validate_package(package):
    _exact_object(package, _EXPECTED_PACKAGE, "controlling_package")
    acquired = _strict_bool(package["acquired"], "controlling_package.acquired")
    digest = _sha_or_none(package["sha256"], "controlling_package.sha256")
    addenda = _strict_bool(package["addenda_complete"], "controlling_package.addenda_complete")
    bound = _strict_bool(package["requirement_register_bound"], "controlling_package.requirement_register_bound")
    if acquired and digest is None:
        raise CarrierError("acquired package requires sha256")
    if not acquired and digest is not None:
        raise CarrierError("unacquired package cannot claim sha256")
    if not acquired and (addenda or bound):
        raise CarrierError("unacquired package cannot claim completeness")
    return {"acquired": acquired, "sha256": digest, "addenda_complete": addenda, "requirement_register_bound": bound}


def _validate_qualification(qualification):
    _exact_object(qualification, _EXPECTED_QUALIFICATION, "qualification")
    conflict = qualification["conflict_disclosure"]
    if conflict not in {"UNKNOWN", "NO_KNOWN_CONFLICT", "DISCLOSED_CONFLICT"}:
        raise CarrierError("qualification.conflict_disclosure invalid")
    return {
        "entity_eligibility_evidence_digest": _sha_or_none(qualification["entity_eligibility_evidence_digest"], "qualification.entity_eligibility_evidence_digest"),
        "insurance_evidence_digest": _sha_or_none(qualification["insurance_evidence_digest"], "qualification.insurance_evidence_digest"),
        "references_evidence_digest": _sha_or_none(qualification["references_evidence_digest"], "qualification.references_evidence_digest"),
        "housing_authority_experience_evidence_digest": _sha_or_none(qualification["housing_authority_experience_evidence_digest"], "qualification.housing_authority_experience_evidence_digest"),
        "conflict_disclosure": conflict,
    }


def _validate_commercial(commercial):
    _exact_object(commercial, _EXPECTED_COMMERCIAL, "commercial")
    currency = commercial["currency"]
    if currency is not None and (type(currency) is not str or not _ISO_CURRENCY.fullmatch(currency)):
        raise CarrierError("commercial.currency must be null or 3-letter uppercase code")
    price = commercial["price_minor"]
    if price is not None:
        price = _strict_int(price, "commercial.price_minor")
    return {
        "currency": currency,
        "price_minor": price,
        "owner_price_confirmed": _strict_bool(commercial["owner_price_confirmed"], "commercial.owner_price_confirmed"),
        "structure_matches_controlling_package": _strict_bool(commercial["structure_matches_controlling_package"], "commercial.structure_matches_controlling_package"),
    }


def _validate_submission(submission):
    _exact_object(submission, _EXPECTED_SUBMISSION, "submission")
    channel = submission["channel"]
    if type(channel) is not str:
        raise CarrierError("submission.channel must be a string")
    owner_ruling = submission["owner_ruling"]
    if owner_ruling not in {"ABSENT", "HOLD", "PROCEED_INTERNAL_ONLY"}:
        raise CarrierError("submission.owner_ruling invalid")
    return {
        "channel": channel,
        "portal_account_verified": _strict_bool(submission["portal_account_verified"], "submission.portal_account_verified"),
        "forms_complete": _strict_bool(submission["forms_complete"], "submission.forms_complete"),
        "owner_ruling": owner_ruling,
        "fresh_portal_state_observed": _strict_bool(submission["fresh_portal_state_observed"], "submission.fresh_portal_state_observed"),
    }


def compile_packet(owner_input):
    top = _exact_object(dict(owner_input), _EXPECTED_TOP, "owner_input")
    if top["source_manifest_digest"] != _SOURCE_DIGEST:
        raise CarrierError("source_manifest_digest mismatch")
    evaluated = _evaluation_time(top["evaluated_at"])
    package = _validate_package(top["controlling_package"])
    qualification = _validate_qualification(top["qualification"])
    commercial = _validate_commercial(top["commercial"])
    submission = _validate_submission(top["submission"])
    tz = _DEADLINE.tzinfo
    questions_open = evaluated.astimezone(tz) <= _QUESTIONS
    deadline_open = evaluated.astimezone(tz) <= _DEADLINE
    package_bound = package["acquired"] and package["sha256"] is not None and package["addenda_complete"] and package["requirement_register_bound"]
    evidence_present = {
        "entity_eligibility": qualification["entity_eligibility_evidence_digest"] is not None,
        "insurance": qualification["insurance_evidence_digest"] is not None,
        "references": qualification["references_evidence_digest"] is not None,
        "housing_authority_experience": qualification["housing_authority_experience_evidence_digest"] is not None,
        "conflict_resolved": qualification["conflict_disclosure"] != "UNKNOWN",
    }
    commercial_complete = commercial["currency"] is not None and commercial["price_minor"] is not None and commercial["owner_price_confirmed"] and commercial["structure_matches_controlling_package"] and package_bound
    channel_matches = submission["channel"] == _BUYER["submission_channel"]
    submission_ready_internal = channel_matches and submission["portal_account_verified"] and submission["forms_complete"] and submission["owner_ruling"] == "PROCEED_INTERNAL_ONLY" and submission["fresh_portal_state_observed"] and package_bound
    blockers = []
    if not deadline_open:
        blockers.append("PROPOSAL_DEADLINE_PASSED")
    if not package_bound:
        blockers.append("CONTROLLING_PACKAGE_NOT_BOUND")
    if not all(evidence_present.values()):
        blockers.append("OWNER_CREDENTIAL_EVIDENCE_INCOMPLETE")
    if not commercial_complete:
        blockers.append("OWNER_PRICING_INCOMPLETE")
    if not channel_matches:
        blockers.append("SUBMISSION_CHANNEL_MISMATCH")
    if not submission_ready_internal:
        blockers.append("SUBMISSION_GATES_INCOMPLETE")
    if _BUYER["evaluation_weights"] is None:
        blockers.append("EVALUATION_REGISTER_UNKNOWN")
    if _BUYER["required_forms"] is None:
        blockers.append("FORM_REGISTER_UNKNOWN")
    if _BUYER["addenda"] is None:
        blockers.append("ADDENDA_REGISTER_UNKNOWN")
    if not deadline_open:
        posture = "NO_BID_DEADLINE_PASSED"
    elif not package_bound:
        posture = "HOLD_CONTROLLING_PACKAGE"
    elif blockers:
        posture = "HOLD_OWNER_EVIDENCE"
    else:
        posture = "OWNER_REVIEW_PACKET_COMPLETE_NOT_SUBMISSION_AUTHORITY"
    packet = {
        "schema": "linden-rfp-26-07-owner-review-packet/v1",
        "source_manifest_digest": _SOURCE_DIGEST,
        "evaluated_at": top["evaluated_at"],
        "buyer": {
            "procuring_entity": _BUYER["procuring_entity"],
            "solicitation_id": _BUYER["solicitation_id"],
            "solicitation_title": _BUYER["solicitation_title"],
            "questions_deadline_local": _BUYER["questions_deadline_local"],
            "proposal_deadline_local": _BUYER["proposal_deadline_local"],
            "submission_channel": _BUYER["submission_channel"],
            "hard_copy_submission_allowed": _BUYER["hard_copy_submission_allowed"],
            "evaluation_weights": _BUYER["evaluation_weights"],
            "required_forms": _BUYER["required_forms"],
            "addenda": _BUYER["addenda"],
            "questions_open_at_evaluation": questions_open,
        },
        "controlling_package": deepcopy(package),
        "qualification": deepcopy(qualification),
        "readiness": {
            "package_bound": package_bound,
            "essential_owner_evidence_present": evidence_present,
            "all_essential_owner_evidence_present": all(evidence_present.values()),
            "commercial_complete": commercial_complete,
        },
        "commercial": deepcopy(commercial),
        "submission": deepcopy(submission),
        "blockers": blockers,
        "posture": posture,
        "authority": deepcopy(_AUTHORITY_FALSE),
    }
    packet["input_digest"] = _digest(top)
    packet["packet_digest"] = _digest(packet)
    return packet


def verify_packet(packet, owner_input):
    if type(packet) is not dict:
        return False
    expected = compile_packet(owner_input)
    return _canonical(dict(packet)) == _canonical(expected)


def example_owner_input():
    return {
        "source_manifest_digest": _SOURCE_DIGEST,
        "evaluated_at": "2026-09-17T01:47:00-04:00",
        "controlling_package": {"acquired": False, "sha256": None, "addenda_complete": False, "requirement_register_bound": False},
        "qualification": {
            "entity_eligibility_evidence_digest": None,
            "insurance_evidence_digest": None,
            "references_evidence_digest": None,
            "housing_authority_experience_evidence_digest": None,
            "conflict_disclosure": "UNKNOWN",
        },
        "commercial": {"currency": None, "price_minor": None, "owner_price_confirmed": False, "structure_matches_controlling_package": False},
        "submission": {
            "channel": _BUYER["submission_channel"],
            "portal_account_verified": False,
            "forms_complete": False,
            "owner_ruling": "ABSENT",
            "fresh_portal_state_observed": False,
        },
    }
