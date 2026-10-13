#!/usr/bin/env python3
"""Truth-narrowed, source-bound healthcare-prime readiness for CPCA HCCN Connect.

The legacy qualifier's subcontract ``TEAMING_READY`` value is retained only as a
diagnostic predecessor signal. This wrapper code-owns the exact legacy qualifier
and canonical CPCA qualification specification, freezes all caller inputs into one
strict plain-JSON snapshot, binds every receipt to the exact evaluated identities,
and keeps both workshare and application readiness at HOLD until separately
provider-authenticated evidence exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

SCHEMA = "cpca-partner-readiness/v3"
MAX_JSON_BYTES = 1_048_576
MAX_PYTHON_BYTES = 1_048_576
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_KEYS = {"source_id", "sha256"}
AUTHORITY = {
    "buyer_contact_authorized": False,
    "credential_use_authorized": False,
    "price_committed": False,
    "staff_committed": False,
    "attestation_signed": False,
    "proposal_submitted": False,
    "award_claimed": False,
    "payment_claimed": False,
    "revenue_claimed": False,
}


def _pairs_no_duplicates(pairs: Sequence[tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _decode_json_object(raw: bytes, label: str) -> Dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f"{label}: JSON exceeds {MAX_JSON_BYTES} bytes")
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_pairs_no_duplicates,
        parse_constant=_reject_json_constant,
    )
    if type(value) is not dict:
        raise ValueError(f"{label}: top-level JSON must be a plain object")
    return value


def _load(path: Path) -> Dict[str, Any]:
    return _decode_json_object(path.read_bytes(), str(path))


def _validate_plain_json(value: Any, label: str = "value") -> None:
    """Reject stateful/custom containers before any trusted semantic read."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{label}: non-finite number is forbidden")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_plain_json(item, f"{label}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError(f"{label}: JSON object keys must be plain strings")
            _validate_plain_json(item, f"{label}.{key}")
        return
    raise ValueError(
        f"{label}: trusted inputs must use only exact plain JSON types; "
        f"got {type(value).__name__}"
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _freeze_json_object(value: Any, label: str) -> Tuple[Dict[str, Any], bytes]:
    """Freeze one caller object into canonical bytes before any semantic read."""
    if type(value) is not dict:
        raise ValueError(f"{label}: trusted input must be a plain JSON object")
    _validate_plain_json(value, label)
    raw = canonical_bytes(value)
    frozen = _decode_json_object(raw, label)
    return frozen, raw


def _clone_frozen_object(raw: bytes, label: str) -> Dict[str, Any]:
    """Return an independent plain-data copy of an already-frozen snapshot."""
    return _decode_json_object(raw, label)


def _canonical_spec_path() -> Path:
    return Path(__file__).resolve().with_name("qualification_spec.json")


def _canonical_legacy_path() -> Path:
    return Path(__file__).resolve().with_name("cpca_qualify.py")


def _assert_canonical_spec(spec: Mapping[str, Any]) -> Tuple[str, str]:
    """Require semantic equality to the repository-owned qualification spec."""
    path = _canonical_spec_path()
    raw = path.read_bytes()
    owned = _decode_json_object(raw, "canonical qualification specification")
    if canonical_bytes(spec) != canonical_bytes(owned):
        raise ValueError("qualification spec differs from code-owned canonical specification")
    return canonical_digest(owned), hashlib.sha256(raw).hexdigest()


def _load_code_owned_legacy() -> Tuple[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]], str]:
    """Load/hash/execute one exact snapshot of the repository-owned predecessor."""
    path = _canonical_legacy_path()
    raw = path.read_bytes()
    if len(raw) > MAX_PYTHON_BYTES:
        raise ValueError("canonical legacy qualifier is too large")
    digest = hashlib.sha256(raw).hexdigest()
    namespace: Dict[str, Any] = {
        "__name__": "cpca_qualify_bound_runtime",
        "__file__": str(path),
        "__package__": None,
    }
    code = compile(raw, str(path), "exec", dont_inherit=True)
    exec(code, namespace, namespace)
    evaluate = namespace.get("evaluate")
    if not callable(evaluate):
        raise ValueError("canonical legacy qualifier does not expose evaluate")
    return evaluate, digest


def _required_gate_ids(spec: Mapping[str, Any], service_type: str) -> List[str]:
    service_map = spec.get("service_type_specific_gate_ids")
    gates = spec.get("mandatory_direct_prime_gates")
    if not isinstance(service_map, dict) or service_type not in service_map:
        raise ValueError(f"unsupported service_type: {service_type!r}")
    if not isinstance(gates, list):
        raise ValueError("mandatory_direct_prime_gates must be a list")
    specific_raw = service_map[service_type]
    if not isinstance(specific_raw, list) or not all(isinstance(x, str) for x in specific_raw):
        raise ValueError(f"service_type {service_type!r} has malformed gate list")
    specific = set(specific_raw)
    track_ids = {"technical_assistance_track_record", "group_training_track_record"}
    out: List[str] = []
    for row in gates:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("mandatory gate row missing string id")
        gate_id = row["id"]
        if gate_id not in track_ids or gate_id in specific:
            out.append(gate_id)
    if not out or len(out) != len(set(out)):
        raise ValueError("required gate ids must be nonempty and unique")
    return out


def _source_object(value: Any, label: str) -> Dict[str, str]:
    if not isinstance(value, dict) or set(value) != SOURCE_KEYS:
        raise ValueError(f"{label} must contain exactly source_id and sha256")
    source_id = value.get("source_id")
    digest = value.get("sha256")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError(f"{label}.source_id must be a nonempty string")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ValueError(f"{label}.sha256 must be lowercase 64-hex")
    return {"source_id": source_id.strip(), "sha256": digest}


def _application_manifest_identity(
    evidence: Mapping[str, Any], required_ids: Sequence[str]
) -> Dict[str, Any]:
    manifest = evidence.get("partner_application_evidence")
    if manifest is None:
        return {
            "present": False,
            "sha256": canonical_digest(None),
            "sources": [],
        }
    if not isinstance(manifest, dict):
        raise ValueError("partner_application_evidence must be an object")

    sources: List[Dict[str, str]] = []
    for key in (
        "prime_identity_source",
        "relationship_authority_source",
        "submission_authority_source",
        "application_package_source",
    ):
        value = manifest.get(key)
        if value is not None:
            normalized = _source_object(value, f"partner_application_evidence.{key}")
            sources.append({"locator": key, **normalized})

    gate_sources = manifest.get("gate_sources")
    if gate_sources is not None and not isinstance(gate_sources, dict):
        raise ValueError("partner_application_evidence.gate_sources must be an object")
    if isinstance(gate_sources, dict):
        unknown = sorted(set(gate_sources) - set(required_ids))
        if unknown:
            raise ValueError(f"unknown partner application gate source ids: {unknown}")
        for gate_id in sorted(gate_sources):
            rows = gate_sources[gate_id]
            if not isinstance(rows, list):
                raise ValueError(f"gate_sources.{gate_id} must be a list")
            seen: set[tuple[str, str]] = set()
            for index, row in enumerate(rows):
                normalized = _source_object(row, f"gate_sources.{gate_id}[{index}]")
                identity = (normalized["source_id"], normalized["sha256"])
                if identity in seen:
                    raise ValueError(f"duplicate source object for gate {gate_id}: {identity[0]}")
                seen.add(identity)
                sources.append({"locator": f"gate_sources.{gate_id}[{index}]", **normalized})

    sources.sort(key=lambda row: (row["locator"], row["source_id"], row["sha256"]))
    return {
        "present": True,
        "sha256": canonical_digest(manifest),
        "sources": sources,
    }


def _application_manifest_blockers(
    spec: Mapping[str, Any], evidence: Mapping[str, Any], required_ids: Sequence[str]
) -> List[str]:
    manifest = evidence.get("partner_application_evidence")
    if manifest is None:
        return ["partner_application_evidence"]
    if not isinstance(manifest, dict):
        raise ValueError("partner_application_evidence must be an object")

    blockers: List[str] = []
    expected_spec_sha = canonical_digest(spec)
    if manifest.get("qualification_spec_sha256") != expected_spec_sha:
        blockers.append("qualification_spec_sha256")

    prime = evidence.get("healthcare_prime")
    prime_name = prime.get("name") if isinstance(prime, dict) else None
    if not isinstance(prime_name, str) or not prime_name.strip():
        blockers.append("healthcare_prime.name")
    elif manifest.get("prime_legal_name") != prime_name.strip():
        blockers.append("prime_legal_name")

    if manifest.get("domain") != evidence.get("domain"):
        blockers.append("domain")
    if manifest.get("service_type") != evidence.get("service_type"):
        blockers.append("service_type")

    for key in (
        "prime_identity_source",
        "relationship_authority_source",
        "submission_authority_source",
        "application_package_source",
    ):
        value = manifest.get(key)
        if value is None:
            blockers.append(key)
        else:
            _source_object(value, f"partner_application_evidence.{key}")

    gate_sources = manifest.get("gate_sources")
    if not isinstance(gate_sources, dict):
        blockers.append("gate_sources")
        gate_sources = {}
    unknown = sorted(set(gate_sources) - set(required_ids))
    if unknown:
        raise ValueError(f"unknown partner application gate source ids: {unknown}")
    for gate_id in required_ids:
        rows = gate_sources.get(gate_id)
        if not isinstance(rows, list) or not rows:
            blockers.append(f"gate_source:{gate_id}")
            continue
        seen: set[tuple[str, str]] = set()
        for index, row in enumerate(rows):
            normalized = _source_object(row, f"gate_sources.{gate_id}[{index}]")
            identity = (normalized["source_id"], normalized["sha256"])
            if identity in seen:
                raise ValueError(f"duplicate source object for gate {gate_id}: {identity[0]}")
            seen.add(identity)
    return blockers


def _prime_identity(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    prime = evidence.get("healthcare_prime")
    if not isinstance(prime, dict):
        return {
            "legal_name": None,
            "eligibility_source": None,
            "safety_net_experience_source": None,
            "relationship_authority": False,
        }
    name = prime.get("name")
    return {
        "legal_name": name.strip() if isinstance(name, str) and name.strip() else None,
        "eligibility_source": prime.get("eligibility_source"),
        "safety_net_experience_source": prime.get("safety_net_experience_source"),
        "relationship_authority": prime.get("relationship_authority") is True,
    }


def _source_packet_identity(spec: Mapping[str, Any]) -> Dict[str, Any]:
    source = spec.get("source_packet")
    if not isinstance(source, dict):
        raise ValueError("canonical spec source_packet must be an object")
    return {
        "gmail_message_id": source.get("gmail_message_id"),
        "filename": source.get("filename"),
        "sha256": source.get("sha256"),
    }


def _compile_trusted_partner_readiness(
    spec: Mapping[str, Any],
    evidence: Mapping[str, Any],
    legacy_result: Mapping[str, Any],
    *,
    spec_sha256: str,
    spec_file_sha256: str,
    legacy_sha256: str,
    evidence_sha256: str,
) -> Dict[str, Any]:
    if evidence.get("bid_model") != "healthcare_prime_subcontract":
        raise ValueError("partner readiness requires bid_model=healthcare_prime_subcontract")
    if not isinstance(legacy_result, dict):
        raise ValueError("legacy_result must be an object")

    legacy_state = legacy_result.get("state")
    legacy_reason = legacy_result.get("reason")
    raw_blockers = legacy_result.get("blockers", [])
    if not isinstance(raw_blockers, list) or not all(isinstance(x, str) and x for x in raw_blockers):
        raise ValueError("legacy blockers must be a list of nonempty strings")
    legacy_blockers = sorted(set(raw_blockers))

    required_ids = _required_gate_ids(spec, str(evidence.get("service_type")))
    gate_status = legacy_result.get("gate_status", {})
    if not isinstance(gate_status, dict):
        gate_status = {}
    non_proven = sorted(gate_id for gate_id in required_ids if gate_status.get(gate_id) != "PROVEN")
    manifest_identity = _application_manifest_identity(evidence, required_ids)

    if legacy_state == "NO_BID":
        workshare_state = "NO_BID"
        workshare_blockers: List[str] = []
        application_state = "NO_BID"
        application_blockers: List[str] = []
        state = "NO_BID"
        reason = "legacy_deadline_or_hard_stop"
    else:
        manifest_blockers = _application_manifest_blockers(spec, evidence, required_ids)
        workshare_state = "HOLD"
        workshare_blockers = sorted(
            set(legacy_blockers + non_proven + ["provider_authenticated_workshare_evidence"])
        )
        application_state = "HOLD"
        application_blockers = sorted(
            set(
                legacy_blockers
                + non_proven
                + manifest_blockers
                + ["provider_authenticated_prime_application_evidence"]
            )
        )
        state = "HOLD"
        reason = (
            "legacy_workshare_signal_unauthenticated"
            if legacy_state == "TEAMING_READY"
            else "workshare_or_prime_signal_unresolved"
        )

    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "state": state,
        "reason": reason,
        "domain": evidence.get("domain"),
        "service_type": evidence.get("service_type"),
        "bid_model": evidence.get("bid_model"),
        "legacy_workshare_signal": {
            "state": legacy_state,
            "reason": legacy_reason,
            "blockers": legacy_blockers,
            "application_authority": False,
            "discussion_authority": False,
            "trusted_code_origin": True,
            "provider_authenticated_evidence": False,
        },
        "workshare": {
            "state": workshare_state,
            "blockers": workshare_blockers,
            "discussion_artifact_only": False,
            "source_bound": False,
            "receipt_bound": True,
            "provider_authenticated_evidence_available": False,
            "caller_evidence_can_authorize_readiness": False,
        },
        "application": {
            "state": application_state,
            "blockers": application_blockers,
            "source_manifest_required": True,
            "provider_authenticated_evidence_available": False,
            "caller_manifest_can_authorize_readiness": False,
        },
        "binding": {
            "qualification_spec_sha256": spec_sha256,
            "qualification_spec_file_sha256": spec_file_sha256,
            "evidence_sha256": evidence_sha256,
            "prime": _prime_identity(evidence),
            "application_manifest": manifest_identity,
            "qualification_source_packet": _source_packet_identity(spec),
            "legacy_implementation": {
                "path": "cpca_qualify.py",
                "sha256": legacy_sha256,
            },
            "legacy_result_sha256": canonical_digest(legacy_result),
        },
        "authority": dict(AUTHORITY),
    }
    if result["workshare"]["state"] == "DISCUSSION_READY":
        raise ValueError("internal invariant: unauthenticated workshare cannot be discussion-ready")
    if result["application"]["state"] == "TEAMING_READY":
        raise ValueError("internal invariant: application readiness is not authorized")
    return result


def compile_partner_readiness(
    spec: Mapping[str, Any],
    evidence: Mapping[str, Any],
    legacy_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compile caller-supplied predecessor data as NON-AUTHORIZING diagnostics."""
    frozen_spec, _ = _freeze_json_object(spec, "spec")
    frozen_evidence, _ = _freeze_json_object(evidence, "evidence")
    frozen_legacy, _ = _freeze_json_object(legacy_result, "legacy_result")
    if frozen_evidence.get("bid_model") != "healthcare_prime_subcontract":
        raise ValueError("partner readiness requires bid_model=healthcare_prime_subcontract")
    blockers = frozen_legacy.get("blockers", [])
    if not isinstance(blockers, list) or not all(isinstance(x, str) and x for x in blockers):
        raise ValueError("legacy blockers must be a list of nonempty strings")
    return {
        "schema": SCHEMA,
        "state": "HOLD",
        "reason": "untrusted_caller_legacy_result",
        "domain": frozen_evidence.get("domain"),
        "service_type": frozen_evidence.get("service_type"),
        "bid_model": frozen_evidence.get("bid_model"),
        "legacy_workshare_signal": {
            "state": frozen_legacy.get("state"),
            "reason": frozen_legacy.get("reason"),
            "blockers": sorted(set(blockers)),
            "application_authority": False,
            "discussion_authority": False,
            "trusted_code_origin": False,
            "provider_authenticated_evidence": False,
        },
        "workshare": {
            "state": "HOLD",
            "blockers": ["trusted_legacy_predecessor_required", "provider_authenticated_workshare_evidence"],
            "discussion_artifact_only": False,
            "source_bound": False,
            "provider_authenticated_evidence_available": False,
            "caller_evidence_can_authorize_readiness": False,
        },
        "application": {
            "state": "HOLD",
            "blockers": ["trusted_legacy_predecessor_required"],
            "source_manifest_required": True,
            "provider_authenticated_evidence_available": False,
            "caller_manifest_can_authorize_readiness": False,
        },
        "binding": {
            "diagnostic_spec_sha256": canonical_digest(frozen_spec),
            "diagnostic_evidence_sha256": canonical_digest(frozen_evidence),
            "diagnostic_legacy_result_sha256": canonical_digest(frozen_legacy),
        },
        "authority": dict(AUTHORITY),
    }


def compile_from_evidence(spec: Mapping[str, Any], evidence: Mapping[str, Any]) -> Dict[str, Any]:
    # Freeze public caller inputs before any semantic read. The predecessor and
    # binder receive independent plain-data clones derived from the same exact
    # canonical byte snapshots so neither caller state nor evaluator mutation can
    # create an evaluation-vs-binding split.
    frozen_spec, spec_snapshot = _freeze_json_object(spec, "spec")
    frozen_evidence, evidence_snapshot = _freeze_json_object(evidence, "evidence")
    spec_sha256, spec_file_sha256 = _assert_canonical_spec(frozen_spec)
    evaluate, legacy_sha256 = _load_code_owned_legacy()

    eval_spec = _clone_frozen_object(spec_snapshot, "frozen spec evaluation snapshot")
    eval_evidence = _clone_frozen_object(evidence_snapshot, "frozen evidence evaluation snapshot")
    legacy_result = evaluate(eval_spec, eval_evidence)

    bound_spec = _clone_frozen_object(spec_snapshot, "frozen spec binding snapshot")
    bound_evidence = _clone_frozen_object(evidence_snapshot, "frozen evidence binding snapshot")
    frozen_legacy, _ = _freeze_json_object(legacy_result, "legacy_result")
    return _compile_trusted_partner_readiness(
        bound_spec,
        bound_evidence,
        frozen_legacy,
        spec_sha256=spec_sha256,
        spec_file_sha256=spec_file_sha256,
        legacy_sha256=legacy_sha256,
        evidence_sha256=hashlib.sha256(evidence_snapshot).hexdigest(),
    )


def make_receipt(spec: Mapping[str, Any], evidence: Mapping[str, Any]) -> Dict[str, Any]:
    result = compile_from_evidence(spec, evidence)
    result["receipt_sha256"] = canonical_digest(result)
    return result


def verify_receipt(
    spec: Mapping[str, Any], evidence: Mapping[str, Any], receipt: Mapping[str, Any]
) -> bool:
    try:
        frozen_receipt, _ = _freeze_json_object(receipt, "receipt")
        supplied = dict(frozen_receipt)
        supplied_digest = supplied.pop("receipt_sha256", None)
        if not isinstance(supplied_digest, str) or supplied_digest != canonical_digest(supplied):
            return False
        expected = make_receipt(spec, evidence)
        return canonical_bytes(expected) == canonical_bytes(frozen_receipt)
    except (TypeError, ValueError, UnicodeError, OSError):
        return False


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    spec = _load(_canonical_spec_path())
    evidence = _load(args.evidence)
    receipt = make_receipt(spec, evidence)
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
