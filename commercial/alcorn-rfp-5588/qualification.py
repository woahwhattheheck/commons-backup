#!/usr/bin/env python3
"""Source-bound qualification engine for Alcorn State RFP #5588.

This module evaluates *evidence*, not aspirations. It deliberately cannot send mail,
submit a proposal, sign certifications, commit pricing, or inherit a partner's
credentials. The buyer packet itself is not stored here; only its digest and normalized
requirements are public.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA = "alcorn-rfp5588-qualification-result/v1"
EVIDENCE_SCHEMA = "alcorn-rfp5588-evidence/v1"
FINAL_STATES = {"PRIME_READY", "TEAMING_READY", "HOLD", "NO_BID"}
MISSING_ARTIFACTS = (
    "section_viii_cost_information",
    "section_ix_references",
    "section_vii_item_12_requirements_matrix",
)
FALSE_AUTHORITY = {
    "buyer_contact_authorized": False,
    "partner_contact_authorized": False,
    "price_release_authorized": False,
    "signature_authorized": False,
    "certification_authorized": False,
    "proposal_submission_authorized": False,
    "contract_acceptance_authorized": False,
    "payment_mutation_authorized": False,
    "award_claimed": False,
    "cash_claimed": False,
    "revenue_claimed": False,
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """Fail-closed evidence/schema error."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise EvidenceError(f"non-finite JSON number is forbidden: {value}")


def load_json_strict(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvidenceError(f"cannot read {path}: {exc}") from exc
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON in {path}: {exc}") from exc
    if type(value) is not dict:
        raise EvidenceError(f"{path}: top-level JSON must be an object")
    return value


def _obj(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{name} must be an object")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if type(value) is not list:
        raise EvidenceError(f"{name} must be an array")
    return value


def _str(value: Any, name: str, *, nonempty: bool = True) -> str:
    if type(value) is not str:
        raise EvidenceError(f"{name} must be a string")
    if nonempty and not value.strip():
        raise EvidenceError(f"{name} must be non-empty")
    return value


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise EvidenceError(f"{name} must be a boolean")
    return value


def _int(value: Any, name: str) -> int:
    if type(value) is not int:
        raise EvidenceError(f"{name} must be an integer (bool is forbidden)")
    return value


def _sha(value: Any, name: str) -> str:
    value = _str(value, name)
    if not SHA256_RE.fullmatch(value):
        raise EvidenceError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def _date(value: Any, name: str) -> dt.date:
    text = _str(value, name)
    try:
        parsed = dt.date.fromisoformat(text)
    except ValueError as exc:
        raise EvidenceError(f"{name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise EvidenceError(f"{name} must use canonical YYYY-MM-DD")
    return parsed


def _when(value: Any, name: str) -> dt.datetime:
    text = _str(value, name)
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise EvidenceError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{name} must include a UTC offset")
    return parsed


def _source_id(value: Any, name: str) -> str:
    text = _str(value, name)
    if len(text) > 240 or any(ord(ch) < 32 for ch in text):
        raise EvidenceError(f"{name} is malformed")
    return text


def _assert_keys(obj: Mapping[str, Any], *, allowed: set[str], required: set[str], name: str) -> None:
    missing = required - set(obj)
    extra = set(obj) - allowed
    if missing:
        raise EvidenceError(f"{name} missing keys: {sorted(missing)}")
    if extra:
        raise EvidenceError(f"{name} has unknown keys: {sorted(extra)}")


def _validate_source(spec: dict[str, Any], evidence: dict[str, Any]) -> None:
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise EvidenceError(f"evidence.schema must be {EVIDENCE_SCHEMA!r}")
    source = _obj(evidence.get("source_packet"), "source_packet")
    expected = _obj(spec.get("source_packet"), "spec.source_packet")
    _assert_keys(
        source,
        allowed={"gmail_message_id", "filename", "sha256", "page_count"},
        required={"gmail_message_id", "filename", "sha256", "page_count"},
        name="source_packet",
    )
    for key in ("gmail_message_id", "filename"):
        if _str(source[key], f"source_packet.{key}") != expected.get(key):
            raise EvidenceError(f"source packet mismatch for {key}")
    if _sha(source["sha256"], "source_packet.sha256") != expected.get("sha256"):
        raise EvidenceError("source packet mismatch for sha256")
    if _int(source["page_count"], "source_packet.page_count") != expected.get("page_count"):
        raise EvidenceError("source packet mismatch for page_count")


def _artifact_state(evidence: dict[str, Any]) -> tuple[list[str], list[str]]:
    artifacts = _obj(evidence.get("buyer_artifacts"), "buyer_artifacts")
    missing: list[str] = []
    present: list[str] = []
    for artifact_id in MISSING_ARTIFACTS:
        row = _obj(artifacts.get(artifact_id), f"buyer_artifacts.{artifact_id}")
        _assert_keys(
            row,
            allowed={"state", "sha256", "evidence_id"},
            required={"state"},
            name=f"buyer_artifacts.{artifact_id}",
        )
        state = _str(row["state"], f"buyer_artifacts.{artifact_id}.state")
        if state == "MISSING_BUYER_ARTIFACT":
            if "sha256" in row or "evidence_id" in row:
                raise EvidenceError(f"{artifact_id}: missing artifact cannot carry proof")
            missing.append(artifact_id)
        elif state == "PRESENT_SOURCE_BOUND":
            _sha(row.get("sha256"), f"buyer_artifacts.{artifact_id}.sha256")
            _source_id(row.get("evidence_id"), f"buyer_artifacts.{artifact_id}.evidence_id")
            present.append(artifact_id)
        else:
            raise EvidenceError(f"{artifact_id}: unsupported state {state!r}")
    return missing, present


def _proof(obj: dict[str, Any], key: str, blockers: list[str]) -> None:
    value = obj.get(key)
    if type(value) is not str or not value.strip():
        blockers.append(key)
    else:
        _source_id(value, key)


def _bool_proof(obj: dict[str, Any], key: str, evidence_key: str, blockers: list[str]) -> None:
    value = obj.get(key)
    if type(value) is not bool:
        raise EvidenceError(f"{key} must be a boolean")
    if value:
        _source_id(obj.get(evidence_key), evidence_key)
    else:
        blockers.append(key)


def _validate_nvidia_authority(
    partner: dict[str, Any], *, prefix: str, now: dt.date, blockers: list[str]
) -> None:
    allowed = {
        "name", "status", "authorization_evidence_id", "authorization_sha256",
        "effective_date", "expires_date", "scope", "commitment_evidence_id",
        "commitment_current", "commitment_revoked"
    }
    required = {
        "name", "status", "authorization_evidence_id", "authorization_sha256",
        "effective_date", "expires_date", "scope"
    }
    _assert_keys(partner, allowed=allowed, required=required, name=prefix)
    _str(partner["name"], f"{prefix}.name")
    if partner["status"] != "ACTIVE":
        blockers.append(f"{prefix}.active_nvidia_partner")
    _source_id(partner["authorization_evidence_id"], f"{prefix}.authorization_evidence_id")
    _sha(partner["authorization_sha256"], f"{prefix}.authorization_sha256")
    effective = _date(partner["effective_date"], f"{prefix}.effective_date")
    expires = _date(partner["expires_date"], f"{prefix}.expires_date")
    if not (effective <= now <= expires):
        blockers.append(f"{prefix}.nvidia_authorization_current")
    scope = _list(partner["scope"], f"{prefix}.scope")
    scope_norm = {_str(x, f"{prefix}.scope[]").strip().upper() for x in scope}
    if not {"DGX SPARK", "LAB DESIGN"}.issubset(scope_norm):
        blockers.append(f"{prefix}.nvidia_scope_dgx_spark_lab_design")


def _validate_track_record(rows: Any, *, prefix: str, now: dt.date, blockers: list[str]) -> None:
    rows = _list(rows, prefix)
    identities: set[str] = set()
    qualified = 0
    for idx, raw in enumerate(rows):
        row = _obj(raw, f"{prefix}[{idx}]")
        _assert_keys(
            row,
            allowed={"engagement_id", "source", "completed_at", "architected", "deployed", "rolled_out"},
            required={"engagement_id", "source", "completed_at", "architected", "deployed", "rolled_out"},
            name=f"{prefix}[{idx}]",
        )
        identity = _source_id(row["engagement_id"], f"{prefix}[{idx}].engagement_id")
        if identity in identities:
            raise EvidenceError(f"duplicate AI-infrastructure engagement identity: {identity}")
        identities.add(identity)
        _source_id(row["source"], f"{prefix}[{idx}].source")
        completed = _date(row["completed_at"], f"{prefix}[{idx}].completed_at")
        if completed > now:
            raise EvidenceError(f"{prefix}[{idx}].completed_at is in the future")
        flags = [
            _bool(row["architected"], f"{prefix}[{idx}].architected"),
            _bool(row["deployed"], f"{prefix}[{idx}].deployed"),
            _bool(row["rolled_out"], f"{prefix}[{idx}].rolled_out"),
        ]
        if all(flags):
            qualified += 1
    if qualified < 1:
        blockers.append(f"{prefix}.architect_deploy_rollout_track_record")


def _validate_reference_sites(rows: Any, *, prefix: str, blockers: list[str]) -> None:
    rows = _list(rows, prefix)
    identities: set[str] = set()
    callable_sites = 0
    for idx, raw in enumerate(rows):
        row = _obj(raw, f"{prefix}[{idx}]")
        _assert_keys(
            row,
            allowed={"reference_id", "source", "site_available_within_7_days", "region"},
            required={"reference_id", "source", "site_available_within_7_days", "region"},
            name=f"{prefix}[{idx}]",
        )
        identity = _source_id(row["reference_id"], f"{prefix}[{idx}].reference_id")
        if identity in identities:
            raise EvidenceError(f"duplicate reference identity: {identity}")
        identities.add(identity)
        _source_id(row["source"], f"{prefix}[{idx}].source")
        available = _bool(row["site_available_within_7_days"], f"{prefix}[{idx}].site_available_within_7_days")
        _str(row["region"], f"{prefix}[{idx}].region")
        if available:
            callable_sites += 1
    # The received packet's missing Section IX prevents us from inventing a required count.
    # We enforce only the explicit Section VII 7.2.6 ability to provide a reference site.
    if callable_sites < 1:
        blockers.append(f"{prefix}.reference_site_available_within_7_days")


PRIME_ALLOWED_KEYS = {
    "nvidia_partner", "ai_infrastructure_engagements", "references",
    "legal_entity_evidence_id", "certificate_of_liability_insurance_evidence_id",
    "everify_evidence_id", "taxpayer_id_confirmation_evidence_id",
    "order_remit_address_evidence_id", "amendments_review_evidence_id",
    "insurance_expires_date", "pricing_approved", "pricing_approval_evidence_id",
    "signature_officer_ready", "signature_officer_evidence_id",
    "sealed_delivery_plan_ready", "sealed_delivery_plan_evidence_id",
    "training_sample_ready", "training_sample_evidence_id",
    "warranty_support_ready", "warranty_support_evidence_id",
}

PRIME_REQUIRED_KEYS = {
    "nvidia_partner", "ai_infrastructure_engagements", "references",
    "pricing_approved", "signature_officer_ready", "sealed_delivery_plan_ready",
    "training_sample_ready", "warranty_support_ready",
}


def _validate_prime_shape(entity: dict[str, Any], *, prefix: str) -> None:
    _assert_keys(
        entity, allowed=PRIME_ALLOWED_KEYS, required=PRIME_REQUIRED_KEYS, name=prefix
    )


def _validate_operational(entity: dict[str, Any], *, prefix: str, due: dt.datetime, blockers: list[str]) -> None:
    for key in (
        "legal_entity_evidence_id", "certificate_of_liability_insurance_evidence_id",
        "everify_evidence_id", "taxpayer_id_confirmation_evidence_id",
        "order_remit_address_evidence_id", "amendments_review_evidence_id",
    ):
        _proof(entity, key, blockers)
    expiry_raw = entity.get("insurance_expires_date")
    if expiry_raw is None:
        blockers.append(f"{prefix}.insurance_current_through_due_date")
    else:
        expiry = _date(expiry_raw, f"{prefix}.insurance_expires_date")
        if expiry < due.date():
            blockers.append(f"{prefix}.insurance_current_through_due_date")
    _bool_proof(entity, "pricing_approved", "pricing_approval_evidence_id", blockers)
    _bool_proof(entity, "signature_officer_ready", "signature_officer_evidence_id", blockers)
    _bool_proof(entity, "sealed_delivery_plan_ready", "sealed_delivery_plan_evidence_id", blockers)
    _bool_proof(entity, "training_sample_ready", "training_sample_evidence_id", blockers)
    _bool_proof(entity, "warranty_support_ready", "warranty_support_evidence_id", blockers)


def _validate_support_scope(scope: Any, blockers: list[str]) -> None:
    scope = _obj(scope, "tjlabs_support")
    _assert_keys(
        scope,
        allowed={"commitment_current", "commitment_evidence_id", "workshare_evidence_id", "capabilities"},
        required={"commitment_current", "commitment_evidence_id", "workshare_evidence_id", "capabilities"},
        name="tjlabs_support",
    )
    if not _bool(scope["commitment_current"], "tjlabs_support.commitment_current"):
        blockers.append("tjlabs_support.commitment_current")
    _source_id(scope["commitment_evidence_id"], "tjlabs_support.commitment_evidence_id")
    _source_id(scope["workshare_evidence_id"], "tjlabs_support.workshare_evidence_id")
    capabilities = _list(scope["capabilities"], "tjlabs_support.capabilities")
    capset = {_str(x, "tjlabs_support.capabilities[]").strip() for x in capabilities}
    if not capset:
        blockers.append("tjlabs_support.capabilities")
    forbidden = {"NVIDIA_PARTNER_STATUS", "OEM_RESALE_AUTHORITY", "HARDWARE_WARRANTY_AUTHORITY"}
    if capset & forbidden:
        raise EvidenceError("TJLabs support scope attempts to inherit prime/OEM authority")


def evaluate(spec: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    _validate_source(spec, evidence)
    allowed_top = {
        "schema", "source_packet", "current_time", "bid_model", "buyer_artifacts",
        "direct_prime", "nvidia_prime", "tjlabs_support", "explicit_disqualifier"
    }
    _assert_keys(
        evidence,
        allowed=allowed_top,
        required={"schema", "source_packet", "current_time", "bid_model", "buyer_artifacts"},
        name="evidence",
    )
    now = _when(evidence["current_time"], "current_time")
    due = _when(spec["opportunity"]["due_at"], "spec.opportunity.due_at")
    missing_artifacts, present_artifacts = _artifact_state(evidence)

    explicit = evidence.get("explicit_disqualifier")
    if explicit is not None:
        row = _obj(explicit, "explicit_disqualifier")
        _assert_keys(row, allowed={"fact", "source"}, required={"fact", "source"}, name="explicit_disqualifier")
        fact = _str(row["fact"], "explicit_disqualifier.fact")
        source = _source_id(row["source"], "explicit_disqualifier.source")
        return _result(
            state="NO_BID", reason="source_bound_explicit_disqualifier", now=now, due=due,
            bid_model=_str(evidence["bid_model"], "bid_model"), blockers=[],
            missing_artifacts=missing_artifacts, present_artifacts=present_artifacts,
            facts={"disqualifying_fact": fact, "disqualifying_source": source},
        )

    if now > due:
        return _result(
            state="NO_BID", reason="deadline_passed", now=now, due=due,
            bid_model=_str(evidence["bid_model"], "bid_model"), blockers=[],
            missing_artifacts=missing_artifacts, present_artifacts=present_artifacts,
        )

    blockers: list[str] = [f"buyer_artifact:{x}" for x in missing_artifacts]
    bid_model = _str(evidence["bid_model"], "bid_model")
    if bid_model == "direct_prime":
        prime = _obj(evidence.get("direct_prime"), "direct_prime")
        _validate_prime_shape(prime, prefix="direct_prime")
        _validate_nvidia_authority(
            _obj(prime.get("nvidia_partner"), "direct_prime.nvidia_partner"),
            prefix="direct_prime.nvidia_partner", now=now.date(), blockers=blockers,
        )
        _validate_track_record(prime.get("ai_infrastructure_engagements"), prefix="direct_prime.ai_infrastructure_engagements", now=now.date(), blockers=blockers)
        _validate_reference_sites(prime.get("references"), prefix="direct_prime.references", blockers=blockers)
        _validate_operational(prime, prefix="direct_prime", due=due, blockers=blockers)
        state = "PRIME_READY" if not blockers else "HOLD"
        reason = "all_internal_direct_prime_gates_proven" if not blockers else "direct_prime_gates_unproven"
    elif bid_model == "nvidia_prime_subcontract":
        prime = _obj(evidence.get("nvidia_prime"), "nvidia_prime")
        _validate_prime_shape(prime, prefix="nvidia_prime")
        partner = _obj(prime.get("nvidia_partner"), "nvidia_prime.nvidia_partner")
        _validate_nvidia_authority(partner, prefix="nvidia_prime.nvidia_partner", now=now.date(), blockers=blockers)
        if not _bool(partner.get("commitment_current"), "nvidia_prime.nvidia_partner.commitment_current"):
            blockers.append("nvidia_prime.nvidia_partner.commitment_current")
        if _bool(partner.get("commitment_revoked"), "nvidia_prime.nvidia_partner.commitment_revoked"):
            blockers.append("nvidia_prime.nvidia_partner.commitment_not_revoked")
        _source_id(partner.get("commitment_evidence_id"), "nvidia_prime.nvidia_partner.commitment_evidence_id")
        _validate_track_record(prime.get("ai_infrastructure_engagements"), prefix="nvidia_prime.ai_infrastructure_engagements", now=now.date(), blockers=blockers)
        _validate_reference_sites(prime.get("references"), prefix="nvidia_prime.references", blockers=blockers)
        _validate_operational(prime, prefix="nvidia_prime", due=due, blockers=blockers)
        _validate_support_scope(evidence.get("tjlabs_support"), blockers)
        state = "TEAMING_READY" if not blockers else "HOLD"
        reason = "named_committed_nvidia_prime_and_support_scope_proven" if not blockers else "teaming_gates_unproven"
    else:
        raise EvidenceError(f"unsupported bid_model: {bid_model!r}")

    return _result(
        state=state, reason=reason, now=now, due=due, bid_model=bid_model,
        blockers=blockers, missing_artifacts=missing_artifacts, present_artifacts=present_artifacts,
    )


def _result(
    *, state: str, reason: str, now: dt.datetime, due: dt.datetime, bid_model: str,
    blockers: list[str], missing_artifacts: list[str], present_artifacts: list[str],
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in FINAL_STATES:
        raise EvidenceError(f"invalid derived state: {state}")
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "state": state,
        "reason": reason,
        "bid_model": bid_model,
        "evaluated_at": now.isoformat(),
        "due_at": due.isoformat(),
        "missing_buyer_artifacts": sorted(missing_artifacts),
        "present_buyer_artifacts": sorted(present_artifacts),
        "blockers": sorted(set(blockers)),
        "authority": dict(FALSE_AUTHORITY),
    }
    if facts:
        out["facts"] = facts
    return out


def canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--spec", type=Path, default=Path(__file__).with_name("qualification_spec.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    spec = load_json_strict(args.spec)
    evidence = load_json_strict(args.evidence)
    result = evaluate(spec, evidence)
    result["receipt_sha256"] = canonical_digest(result)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
