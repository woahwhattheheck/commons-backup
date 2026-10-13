from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from typing import Any

SCHEMA = "TJL_PROCUREMENT_QUALIFICATION_V1"
RESULT_SCHEMA = "TJL_PROCUREMENT_QUALIFICATION_RESULT_V1"
BUNDLE_SCHEMA = "TJL_PROCUREMENT_QUALIFICATION_BUNDLE_V1"
TRUTH_BOUNDARY = (
    "INTERNAL_PURSUIT_POSTURE_ONLY_NOT_BUYER_SCORING_NOT_WIN_PROBABILITY"
)

PROOF_STATES = frozenset({"PROVEN", "UNPROVEN", "FAILED", "NOT_REQUIRED"})
SOURCE_KINDS = frozenset(
    {"CONTROLLING_PACKET", "OFFICIAL_NOTICE", "FIRST_PARTY_VENDOR", "SECONDARY"}
)
PRIME_GATES = (
    "past_performance",
    "reference_coverage",
    "organizational_continuity",
    "insurance_evidence",
    "security_assurance",
    "deployed_product_proof",
    "support_capacity",
    "financial_contract_capacity",
)
WORKSHARE_GATES = (
    "bounded_specialist_scope",
    "specialist_delivery_evidence",
    "paid_route_defined",
)

AUTHORITY_ITEMS = (
    ("external_send", False),
    ("recipient_selection", False),
    ("muse_selection", False),
    ("pricing_commitment", False),
    ("bid_submission", False),
    ("signature", False),
    ("contract_acceptance", False),
    ("provider_mutation", False),
    ("payment_movement", False),
    ("receivable_establishment", False),
    ("accounting_assertion", False),
    ("revenue_recognition", False),
)

DOCUMENT_KEYS = frozenset(
    {
        "schema",
        "evaluation_at",
        "max_source_age_hours",
        "opportunity",
        "mandatory_requirements",
        "prime_readiness",
        "workshare_readiness",
        "economics",
    }
)
OPPORTUNITY_KEYS = frozenset(
    {
        "opportunity_id",
        "buyer",
        "scope_label",
        "pursuit_open",
        "deadline_at",
        "source_kind",
        "source_observed_at",
        "source_ref",
        "source_sha256",
        "controlling_packet_available",
    }
)
REQUIREMENT_KEYS = frozenset(
    {
        "requirement_id",
        "description",
        "applies_to_prime",
        "applies_to_workshare",
        "state",
        "evidence_ref",
    }
)
ECONOMICS_KEYS = frozenset(
    {
        "proposed_workshare_value_cents",
        "minimum_workshare_value_cents",
        "estimated_pursuit_cost_cents",
        "pursuit_cost_cap_cents",
    }
)


class QualificationError(ValueError):
    pass


def _authority() -> dict[str, bool]:
    return dict(AUTHORITY_ITEMS)


def _exact(value: Any, keys: frozenset[str] | set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise QualificationError(f"{where}: exact object required")
    have, want = set(value), set(keys)
    if have != want:
        raise QualificationError(
            f"{where}: exact keys required; missing={sorted(want-have)}; extra={sorted(have-want)}"
        )
    return value


def _text(value: Any, where: str, maximum: int = 1024, *, allow_empty: bool = False) -> str:
    if type(value) is not str or len(value) > maximum or (not allow_empty and not value):
        raise QualificationError(f"{where}: bounded string required")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise QualificationError(f"{where}: control characters forbidden")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise QualificationError(f"{where}: boolean required")
    return value


def _uint(value: Any, where: str, maximum: int = 10**15) -> int:
    if type(value) is bool or type(value) is not int or value < 0 or value > maximum:
        raise QualificationError(f"{where}: bounded nonnegative integer required")
    return value


def _sha(value: Any, where: str) -> str:
    text = _text(value, where, 64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise QualificationError(f"{where}: lowercase sha256 required")
    return text


def _time(value: Any, where: str) -> datetime:
    text = _text(value, where, 40)
    if "." in text or not text.endswith("Z"):
        raise QualificationError(f"{where}: whole-second UTC RFC3339 Z required")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise QualificationError(f"{where}: invalid timestamp") from exc


def _proof(value: Any, where: str) -> dict[str, str]:
    row = _exact(value, {"state", "evidence_ref"}, where)
    state = _text(row["state"], f"{where}.state", 32)
    if state not in PROOF_STATES:
        raise QualificationError(f"{where}.state: unsupported proof state")
    ref = _text(row["evidence_ref"], f"{where}.evidence_ref", 1024, allow_empty=True)
    if state == "PROVEN" and not ref:
        raise QualificationError(f"{where}: PROVEN requires evidence_ref")
    if state == "NOT_REQUIRED" and ref:
        raise QualificationError(f"{where}: NOT_REQUIRED must not carry evidence_ref")
    return {"state": state, "evidence_ref": ref}


def _proof_map(value: Any, keys: tuple[str, ...], where: str) -> dict[str, dict[str, str]]:
    row = _exact(value, set(keys), where)
    return {key: _proof(row[key], f"{where}.{key}") for key in keys}


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise QualificationError(f"not canonical JSON: {exc}") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _gate_ok(proof: dict[str, str]) -> bool:
    return proof["state"] in {"PROVEN", "NOT_REQUIRED"}


def _blocker(prefix: str, name: str, state: str) -> str:
    return f"{prefix}_{name.upper()}_{state}"


def compile_assessment(document: Any) -> dict[str, Any]:
    doc = _exact(document, DOCUMENT_KEYS, "document")
    if doc["schema"] != SCHEMA:
        raise QualificationError("document.schema: unsupported")

    evaluation_at = _time(doc["evaluation_at"], "document.evaluation_at")
    max_age = _uint(doc["max_source_age_hours"], "document.max_source_age_hours", 24 * 365)
    if max_age == 0:
        raise QualificationError("document.max_source_age_hours: must be positive")

    opportunity = _exact(doc["opportunity"], OPPORTUNITY_KEYS, "opportunity")
    opportunity_id = _text(opportunity["opportunity_id"], "opportunity.opportunity_id", 160)
    buyer = _text(opportunity["buyer"], "opportunity.buyer", 240)
    scope_label = _text(opportunity["scope_label"], "opportunity.scope_label", 320)
    pursuit_open = _bool(opportunity["pursuit_open"], "opportunity.pursuit_open")
    deadline = _time(opportunity["deadline_at"], "opportunity.deadline_at")
    observed = _time(opportunity["source_observed_at"], "opportunity.source_observed_at")
    if observed > evaluation_at:
        raise QualificationError("opportunity.source_observed_at: future evidence")
    source_kind = _text(opportunity["source_kind"], "opportunity.source_kind", 40)
    if source_kind not in SOURCE_KINDS:
        raise QualificationError("opportunity.source_kind: unsupported")
    source_ref = _text(opportunity["source_ref"], "opportunity.source_ref", 1024)
    source_sha = _sha(opportunity["source_sha256"], "opportunity.source_sha256")
    controlling = _bool(
        opportunity["controlling_packet_available"],
        "opportunity.controlling_packet_available",
    )
    if controlling and source_kind != "CONTROLLING_PACKET":
        raise QualificationError(
            "opportunity: controlling_packet_available requires CONTROLLING_PACKET source_kind"
        )

    age_seconds = int((evaluation_at - observed).total_seconds())
    source_fresh = age_seconds <= max_age * 3600
    deadline_open = evaluation_at <= deadline

    raw_requirements = doc["mandatory_requirements"]
    if type(raw_requirements) is not list:
        raise QualificationError("document.mandatory_requirements: array required")
    requirements: list[dict[str, Any]] = []
    ids: set[str] = set()
    for idx, raw in enumerate(raw_requirements):
        row = _exact(raw, REQUIREMENT_KEYS, f"mandatory_requirements[{idx}]")
        rid = _text(row["requirement_id"], f"mandatory_requirements[{idx}].requirement_id", 120)
        if rid in ids:
            raise QualificationError(f"duplicate mandatory requirement_id: {rid}")
        ids.add(rid)
        state = _text(row["state"], f"{rid}.state", 32)
        if state not in PROOF_STATES:
            raise QualificationError(f"{rid}.state: unsupported proof state")
        ref = _text(row["evidence_ref"], f"{rid}.evidence_ref", 1024, allow_empty=True)
        if state == "PROVEN" and not ref:
            raise QualificationError(f"{rid}: PROVEN requires evidence_ref")
        if state == "NOT_REQUIRED" and ref:
            raise QualificationError(f"{rid}: NOT_REQUIRED must not carry evidence_ref")
        requirements.append(
            {
                "requirement_id": rid,
                "description": _text(row["description"], f"{rid}.description", 512),
                "applies_to_prime": _bool(row["applies_to_prime"], f"{rid}.applies_to_prime"),
                "applies_to_workshare": _bool(
                    row["applies_to_workshare"], f"{rid}.applies_to_workshare"
                ),
                "state": state,
                "evidence_ref": ref,
            }
        )

    prime = _proof_map(doc["prime_readiness"], PRIME_GATES, "prime_readiness")
    workshare = _proof_map(
        doc["workshare_readiness"], WORKSHARE_GATES, "workshare_readiness"
    )

    economics = _exact(doc["economics"], ECONOMICS_KEYS, "economics")
    proposed_value = _uint(
        economics["proposed_workshare_value_cents"],
        "economics.proposed_workshare_value_cents",
    )
    minimum_value = _uint(
        economics["minimum_workshare_value_cents"],
        "economics.minimum_workshare_value_cents",
    )
    pursuit_cost = _uint(
        economics["estimated_pursuit_cost_cents"],
        "economics.estimated_pursuit_cost_cents",
    )
    cost_cap = _uint(
        economics["pursuit_cost_cap_cents"],
        "economics.pursuit_cost_cap_cents",
    )
    workshare_value_meets_floor = proposed_value >= minimum_value
    pursuit_cost_within_cap = pursuit_cost <= cost_cap

    prime_blockers: list[str] = []
    workshare_blockers: list[str] = []

    if not pursuit_open:
        prime_blockers.append("OPPORTUNITY_NOT_OPEN")
        workshare_blockers.append("OPPORTUNITY_NOT_OPEN")
    if not deadline_open:
        prime_blockers.append("DEADLINE_PASSED")
        workshare_blockers.append("DEADLINE_PASSED")
    if not source_fresh:
        prime_blockers.append("SOURCE_STALE")
        workshare_blockers.append("SOURCE_STALE_REFRESH_REQUIRED")
    if not controlling:
        prime_blockers.append("CONTROLLING_PACKET_NOT_AVAILABLE")

    for req in requirements:
        if req["applies_to_prime"] and req["state"] not in {"PROVEN", "NOT_REQUIRED"}:
            prime_blockers.append(_blocker("MANDATORY", req["requirement_id"], req["state"]))
        if req["applies_to_workshare"] and req["state"] not in {"PROVEN", "NOT_REQUIRED"}:
            workshare_blockers.append(
                _blocker("WORKSHARE_MANDATORY", req["requirement_id"], req["state"])
            )

    for name in PRIME_GATES:
        if not _gate_ok(prime[name]):
            prime_blockers.append(_blocker("PRIME", name, prime[name]["state"]))
    for name in WORKSHARE_GATES:
        if not _gate_ok(workshare[name]):
            workshare_blockers.append(
                _blocker("WORKSHARE", name, workshare[name]["state"])
            )

    if proposed_value < minimum_value:
        workshare_blockers.append("WORKSHARE_VALUE_BELOW_FLOOR")
    if pursuit_cost > cost_cap:
        prime_blockers.append("PURSUIT_COST_EXCEEDS_CAP")
        workshare_blockers.append("PURSUIT_COST_EXCEEDS_CAP")

    prime_eligible = not prime_blockers
    workshare_eligible = not workshare_blockers

    terminal_no_bid = (
        not pursuit_open
        or not deadline_open
        or pursuit_cost > cost_cap
    )

    if prime_eligible:
        decision = "PRIME_READY"
    elif workshare_eligible:
        decision = "WORKSHARE_ONLY"
    else:
        decision = "NO_BID"

    if terminal_no_bid:
        decision = "NO_BID"

    if decision == "PRIME_READY":
        next_actions = [
            "OWNER_REVIEW_PRIME_POSTURE",
            "RETAIN_EXACT_BUYER_AND_DELIVERY_EVIDENCE",
            "FRESH_COLLISION_CENSUS_AND_MUSE_BEFORE_ANY_OUTBOUND",
        ]
    elif decision == "WORKSHARE_ONLY":
        next_actions = [
            "PACKAGE_BOUNDED_PAID_SPECIALIST_SCOPE",
            "TARGET_QUALIFIED_PRIME_NOT_BUYER_AS_DIRECT_PRIME",
            "FRESH_COLLISION_CENSUS_AND_MUSE_BEFORE_ANY_OUTBOUND",
        ]
    else:
        next_actions = [
            "DO_NOT_SPEND_FURTHER_PURSUIT_BUDGET",
            "REOPEN_ONLY_ON_NEW_CONTROLLING_EVIDENCE_OR_ECONOMIC_CHANGE",
        ]

    return {
        "schema": RESULT_SCHEMA,
        "evaluation_at": evaluation_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "truth_boundary": TRUTH_BOUNDARY,
        "opportunity": {
            "opportunity_id": opportunity_id,
            "buyer": buyer,
            "scope_label": scope_label,
            "deadline_at": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deadline_open": deadline_open,
            "source_kind": source_kind,
            "source_observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_age_seconds": age_seconds,
            "source_fresh": source_fresh,
            "source_ref": source_ref,
            "source_sha256": source_sha,
            "controlling_packet_available": controlling,
            "pursuit_open": pursuit_open,
        },
        "decision": decision,
        "prime": {
            "eligible": prime_eligible and not terminal_no_bid,
            "blockers": sorted(set(prime_blockers)),
            "readiness": prime,
        },
        "workshare": {
            "eligible": workshare_eligible and not terminal_no_bid,
            "blockers": sorted(set(workshare_blockers)),
            "readiness": workshare,
        },
        "mandatory_requirements": sorted(
            requirements, key=lambda row: row["requirement_id"]
        ),
        "economics": {
            "proposed_workshare_value_cents": proposed_value,
            "minimum_workshare_value_cents": minimum_value,
            "estimated_pursuit_cost_cents": pursuit_cost,
            "pursuit_cost_cap_cents": cost_cap,
            "workshare_value_meets_floor": workshare_value_meets_floor,
            "pursuit_cost_within_cap": pursuit_cost_within_cap,
        },
        "next_actions": next_actions,
        "authority": _authority(),
    }


def compile_bundle(document: Any) -> dict[str, Any]:
    normalized = json.loads(_canonical(document).decode("utf-8"))
    assessment = compile_assessment(normalized)
    return {
        "schema": BUNDLE_SCHEMA,
        "input": normalized,
        "assessment": assessment,
        "receipt": {
            "schema": BUNDLE_SCHEMA,
            "input_sha256": _digest(normalized),
            "assessment_sha256": _digest(assessment),
            "authority": _authority(),
        },
    }


def verify_bundle(bundle: Any) -> bool:
    if type(bundle) is not dict or set(bundle) != {
        "schema",
        "input",
        "assessment",
        "receipt",
    }:
        return False
    if bundle.get("schema") != BUNDLE_SCHEMA:
        return False
    receipt = bundle.get("receipt")
    if type(receipt) is not dict or set(receipt) != {
        "schema",
        "input_sha256",
        "assessment_sha256",
        "authority",
    }:
        return False
    if receipt.get("schema") != BUNDLE_SCHEMA or receipt.get("authority") != _authority():
        return False
    try:
        return _canonical(compile_bundle(bundle["input"])) == _canonical(bundle)
    except (QualificationError, TypeError, ValueError, KeyError):
        return False


def load_json_strict(stream: Any) -> Any:
    def reject_constant(value: str) -> None:
        raise QualificationError(f"non-finite JSON constant: {value}")

    def reject_float(value: str) -> None:
        raise QualificationError(f"floating JSON number forbidden: {value}")

    def bounded_int(value: str) -> int:
        digits = value[1:] if value.startswith("-") else value
        if len(digits) > 18:
            raise QualificationError("JSON integer exceeds bound")
        return int(value)

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise QualificationError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    raw = stream.read(8_000_001)
    if type(raw) is not str or len(raw.encode("utf-8", "strict")) > 8_000_000:
        raise QualificationError("input exceeds bound")
    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
            parse_int=bounded_int,
        )
    except json.JSONDecodeError as exc:
        raise QualificationError(f"invalid strict JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evidence-bound procurement prime/workshare qualification gate"
    )
    parser.add_argument("command", choices=("compile", "verify"))
    args = parser.parse_args(argv)
    try:
        value = load_json_strict(sys.stdin)
        if args.command == "compile":
            sys.stdout.write(_canonical(compile_bundle(value)).decode("utf-8") + "\n")
            return 0
        if not verify_bundle(value):
            raise QualificationError("bundle verification failed")
        return 0
    except (QualificationError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
