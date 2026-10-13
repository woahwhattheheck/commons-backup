"""Fail-closed authority facade for the opportunity qualification core.

The deterministic v1 core remains byte-preserved.  This facade adds an
independently retained package-completeness trust root which binds both the
complete gate set and every buyer-source descriptor capable of influencing
qualification authority.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import engine_core as _core
from engine_core import *  # noqa: F401,F403 - preserve the public v1 surface

COMPLETENESS_CONTRACT = "tjlabs.opportunity-qualification-completeness/v2"
_COMPLETENESS_KEYS = {
    "contract", "opportunity_id", "controlling_source_id",
    "controlling_source_sha256", "extracted_at", "extraction_evidence_sha256",
    "complete", "gate_count", "gate_set_sha256", "gates",
    "authority_source_count", "authority_source_set_sha256", "authority_sources",
}
_COMPLETENESS_GATE_KEYS = {
    "gate_id", "category", "mandatory", "route", "cure", "buyer_source_id",
    "buyer_source_sha256", "description_sha256",
}
_AUTHORITY_SOURCE_KEYS = {
    "source_id", "scope", "source_class", "url", "captured_at", "sha256",
}

_original_compile = _core.compile_qualification
_original_validate_requirement = _core._validate_requirement


def _evaluate_team(requirements, sources, teaming, teaming_source_id):
    if teaming == "UNKNOWN" or not _core._buyer_official(teaming_source_id, sources):
        return False, True, ["TEAMING_NOT_OFFICIALLY_EVIDENCED"]
    if teaming == "PROHIBITED":
        return False, False, ["TEAMING_PROHIBITED"]
    return _core._evaluate_team_official_allowed(requirements, sources)


def _evaluate_team_official_allowed(requirements, sources):
    ready = True
    possible = True
    reasons = []
    for req in requirements:
        if not req["mandatory"]:
            continue
        prefix = req["gate_id"]
        if not _core._buyer_official(req["buyer_source_id"], sources):
            ready = False
            reasons.append(f"{prefix}:MANDATORY_SOURCE_NOT_OFFICIAL")
            continue

        route = req["route"]
        prime_state = req["prime_state"]
        team_state = req["team_state"]
        cure = req["cure"]

        if route == "PRIME":
            if prime_state == "PASS":
                continue
            if cure == "PARTNER" and team_state == "PASS":
                continue
            ready = False
            if prime_state == "FAIL" and cure == "NONE":
                possible = False
                reasons.append(f"{prefix}:NONCURABLE_PRIME_FAILURE")
            elif cure == "PARTNER" and team_state == "FAIL":
                possible = False
                reasons.append(f"{prefix}:PARTNER_CURE_FAILED")
            else:
                reasons.append(f"{prefix}:TEAM_ROUTE_MISSING_CURE")
            continue

        if route == "TEAM":
            if team_state == "PASS":
                continue
            ready = False
            if team_state == "FAIL":
                possible = False
                reasons.append(f"{prefix}:TEAM_FAILED")
            else:
                reasons.append(f"{prefix}:TEAM_MISSING")
            continue

        side_fail = False
        if prime_state != "PASS":
            ready = False
            side_fail = side_fail or prime_state == "FAIL"
            reasons.append(f"{prefix}:PRIME_{'FAILED' if prime_state == 'FAIL' else 'MISSING'}")
        if team_state != "PASS":
            ready = False
            side_fail = side_fail or team_state == "FAIL"
            reasons.append(f"{prefix}:TEAM_{'FAILED' if team_state == 'FAIL' else 'MISSING'}")
        if side_fail:
            possible = False
    return ready, possible, sorted(set(reasons))


_core._evaluate_team_official_allowed = _evaluate_team_official_allowed
_core._evaluate_team = _evaluate_team


def _normalize_completeness_gate(raw: Any, index: int) -> dict[str, Any]:
    path = f"trusted_completeness.gates[{index}]"
    gate = _core._expect_object(raw, path, _COMPLETENESS_GATE_KEYS, _COMPLETENESS_GATE_KEYS)
    return {
        "gate_id": _core._expect_id(gate["gate_id"], f"{path}.gate_id"),
        "category": _core._expect_enum(gate["category"], f"{path}.category", _core._CATEGORIES),
        "mandatory": _core._expect_bool(gate["mandatory"], f"{path}.mandatory"),
        "route": _core._expect_enum(gate["route"], f"{path}.route", _core._ROUTES),
        "cure": _core._expect_enum(gate["cure"], f"{path}.cure", _core._CURES),
        "buyer_source_id": _core._expect_id(gate["buyer_source_id"], f"{path}.buyer_source_id"),
        "buyer_source_sha256": _core._expect_sha(
            gate["buyer_source_sha256"], f"{path}.buyer_source_sha256"
        ),
        "description_sha256": _core._expect_sha(
            gate["description_sha256"], f"{path}.description_sha256"
        ),
    }


def _normalize_authority_source(raw: Any, index: int, *, trusted_as_of: str) -> dict[str, Any]:
    path = f"trusted_completeness.authority_sources[{index}]"
    source = _core._expect_object(raw, path, _AUTHORITY_SOURCE_KEYS, _AUTHORITY_SOURCE_KEYS)
    captured = _core._parse_utc(source["captured_at"], f"{path}.captured_at")
    if captured > _core._parse_utc(trusted_as_of, "trusted_as_of"):
        raise QualificationError(f"{path}.captured_at: future evidence")
    return {
        "source_id": _core._expect_id(source["source_id"], f"{path}.source_id"),
        "scope": _core._expect_enum(source["scope"], f"{path}.scope", _core._SOURCE_SCOPES),
        "source_class": _core._expect_enum(
            source["source_class"], f"{path}.source_class", _core._SOURCE_CLASSES
        ),
        "url": _core._expect_url(source["url"], f"{path}.url"),
        "captured_at": source["captured_at"],
        "sha256": _core._expect_sha(source["sha256"], f"{path}.sha256"),
    }


def _normalize_trusted_completeness(raw: Any, *, trusted_as_of: str) -> dict[str, Any]:
    manifest = _core._expect_object(
        raw, "trusted_completeness", _COMPLETENESS_KEYS, _COMPLETENESS_KEYS
    )
    if (
        _core._expect_text(
            manifest["contract"], "trusted_completeness.contract", max_len=96
        )
        != COMPLETENESS_CONTRACT
    ):
        raise QualificationError("trusted_completeness.contract: unsupported contract")

    extracted_at = _core._parse_utc(
        manifest["extracted_at"], "trusted_completeness.extracted_at"
    )
    if extracted_at > _core._parse_utc(trusted_as_of, "trusted_as_of"):
        raise QualificationError(
            "trusted_completeness.extracted_at: future extraction evidence"
        )

    complete = _core._expect_bool(
        manifest["complete"], "trusted_completeness.complete"
    )

    gate_count = manifest["gate_count"]
    if type(gate_count) is not int or gate_count < 0:
        raise QualificationError(
            "trusted_completeness.gate_count: expected non-negative integer"
        )
    raw_gates = _core._expect_list(
        manifest["gates"], "trusted_completeness.gates"
    )
    normalized_gates = [
        _normalize_completeness_gate(gate, i) for i, gate in enumerate(raw_gates)
    ]
    gates_by_id: dict[str, dict[str, Any]] = {}
    for gate in normalized_gates:
        if gate["gate_id"] in gates_by_id:
            raise QualificationError(
                f"trusted_completeness.gates: duplicate gate_id {gate['gate_id']}"
            )
        gates_by_id[gate["gate_id"]] = gate
    gates = [gates_by_id[key] for key in sorted(gates_by_id)]
    if gate_count != len(gates):
        raise QualificationError(
            "trusted_completeness.gate_count: does not match gates"
        )
    gate_set_sha256 = _core._expect_sha(
        manifest["gate_set_sha256"], "trusted_completeness.gate_set_sha256"
    )
    if gate_set_sha256 != _core.digest(gates):
        raise QualificationError(
            "trusted_completeness.gate_set_sha256: does not match gates"
        )

    authority_source_count = manifest["authority_source_count"]
    if type(authority_source_count) is not int or authority_source_count < 0:
        raise QualificationError(
            "trusted_completeness.authority_source_count: expected non-negative integer"
        )
    raw_sources = _core._expect_list(
        manifest["authority_sources"], "trusted_completeness.authority_sources"
    )
    normalized_sources = [
        _normalize_authority_source(source, i, trusted_as_of=trusted_as_of)
        for i, source in enumerate(raw_sources)
    ]
    sources_by_id: dict[str, dict[str, Any]] = {}
    for source in normalized_sources:
        if source["source_id"] in sources_by_id:
            raise QualificationError(
                "trusted_completeness.authority_sources: duplicate source_id "
                + source["source_id"]
            )
        sources_by_id[source["source_id"]] = source
    authority_sources = [sources_by_id[key] for key in sorted(sources_by_id)]
    if authority_source_count != len(authority_sources):
        raise QualificationError(
            "trusted_completeness.authority_source_count: does not match authority_sources"
        )
    authority_source_set_sha256 = _core._expect_sha(
        manifest["authority_source_set_sha256"],
        "trusted_completeness.authority_source_set_sha256",
    )
    if authority_source_set_sha256 != _core.digest(authority_sources):
        raise QualificationError(
            "trusted_completeness.authority_source_set_sha256: "
            "does not match authority_sources"
        )

    return {
        "contract": COMPLETENESS_CONTRACT,
        "opportunity_id": _core._expect_id(
            manifest["opportunity_id"], "trusted_completeness.opportunity_id"
        ),
        "controlling_source_id": _core._expect_id(
            manifest["controlling_source_id"],
            "trusted_completeness.controlling_source_id",
        ),
        "controlling_source_sha256": _core._expect_sha(
            manifest["controlling_source_sha256"],
            "trusted_completeness.controlling_source_sha256",
        ),
        "extracted_at": manifest["extracted_at"],
        "extraction_evidence_sha256": _core._expect_sha(
            manifest["extraction_evidence_sha256"],
            "trusted_completeness.extraction_evidence_sha256",
        ),
        "complete": complete,
        "gate_count": gate_count,
        "gate_set_sha256": gate_set_sha256,
        "gates": gates,
        "authority_source_count": authority_source_count,
        "authority_source_set_sha256": authority_source_set_sha256,
        "authority_sources": authority_sources,
    }


def _observed_gate_descriptors(packet: dict[str, Any]) -> list[dict[str, Any]]:
    sources = {source["source_id"]: source for source in packet["sources"]}
    gates = []
    for requirement in packet["requirements"]:
        source = sources[requirement["buyer_source_id"]]
        gates.append(
            {
                "gate_id": requirement["gate_id"],
                "category": requirement["category"],
                "mandatory": requirement["mandatory"],
                "route": requirement["route"],
                "cure": requirement["cure"],
                "buyer_source_id": requirement["buyer_source_id"],
                "buyer_source_sha256": source["sha256"],
                "description_sha256": _core.digest(requirement["description"]),
            }
        )
    return sorted(gates, key=lambda gate: gate["gate_id"])


def _authority_source_ids(packet: dict[str, Any]) -> list[str]:
    opportunity = packet["opportunity"]
    ids = {
        opportunity.get("controlling_source_id"),
        opportunity.get("proposal_deadline_source_id"),
        opportunity.get("question_deadline_source_id"),
        opportunity.get("teaming_source_id"),
    }
    ids.update(requirement["buyer_source_id"] for requirement in packet["requirements"])
    return sorted(source_id for source_id in ids if source_id is not None)


def _observed_authority_sources(packet: dict[str, Any]) -> list[dict[str, Any]]:
    sources = {source["source_id"]: source for source in packet["sources"]}
    observed = []
    for source_id in _authority_source_ids(packet):
        source = sources.get(source_id)
        if source is None:
            # Core validation rejects the missing reference. Keep this helper
            # deterministic instead of inventing authority for an absent source.
            continue
        observed.append(
            {
                "source_id": source["source_id"],
                "scope": source["scope"],
                "source_class": source["source_class"],
                "url": source["url"],
                "captured_at": source["captured_at"],
                "sha256": source["sha256"],
            }
        )
    return observed


def _assess_completeness(
    packet: dict[str, Any],
    *,
    trusted_as_of: str,
    trusted_completeness: Any,
    trusted_completeness_sha256: Any,
) -> dict[str, Any]:
    observed_gates = _observed_gate_descriptors(packet)
    observed_gate_digest = _core.digest(observed_gates)
    observed_sources = _observed_authority_sources(packet)
    observed_source_digest = _core.digest(observed_sources)

    if trusted_completeness is None:
        return {
            "provided": False,
            "trust_root_provided": trusted_completeness_sha256 is not None,
            "verified": False,
            "trusted_manifest_sha256": None,
            "manifest_digest": None,
            "extraction_evidence_sha256": None,
            "expected_gate_count": None,
            "observed_gate_count": len(observed_gates),
            "expected_gate_set_sha256": None,
            "observed_gate_set_sha256": observed_gate_digest,
            "expected_authority_source_count": None,
            "observed_authority_source_count": len(observed_sources),
            "expected_authority_source_set_sha256": None,
            "observed_authority_source_set_sha256": observed_source_digest,
            "reasons": ["PACKAGE_COMPLETENESS_NOT_PROVIDED"],
        }

    manifest = _normalize_trusted_completeness(
        trusted_completeness, trusted_as_of=trusted_as_of
    )
    manifest_digest = _core.digest(manifest)
    trusted_manifest_digest = None
    reasons: list[str] = []

    if trusted_completeness_sha256 is None:
        reasons.append("COMPLETENESS_TRUST_ROOT_NOT_PROVIDED")
    else:
        trusted_manifest_digest = _core._expect_sha(
            trusted_completeness_sha256, "trusted_completeness_sha256"
        )
        if trusted_manifest_digest != manifest_digest:
            reasons.append("COMPLETENESS_TRUST_ROOT_MISMATCH")

    opportunity = packet["opportunity"]
    sources = {source["source_id"]: source for source in packet["sources"]}
    if manifest["opportunity_id"] != opportunity["opportunity_id"]:
        reasons.append("COMPLETENESS_OPPORTUNITY_MISMATCH")

    controlling_id = opportunity["controlling_source_id"]
    controlling = sources.get(controlling_id) if controlling_id is not None else None
    if (
        manifest["controlling_source_id"] != controlling_id
        or controlling is None
        or manifest["controlling_source_sha256"] != controlling["sha256"]
    ):
        reasons.append("COMPLETENESS_CONTROLLING_SOURCE_MISMATCH")

    if not manifest["complete"]:
        reasons.append("PACKAGE_EXTRACTION_INCOMPLETE")
    if (
        manifest["gate_count"] != len(observed_gates)
        or manifest["gate_set_sha256"] != observed_gate_digest
    ):
        reasons.append("PACKAGE_GATE_SET_MISMATCH")
    if (
        manifest["authority_source_count"] != len(observed_sources)
        or manifest["authority_source_set_sha256"] != observed_source_digest
    ):
        reasons.append("PACKAGE_AUTHORITY_SOURCE_SET_MISMATCH")

    return {
        "provided": True,
        "trust_root_provided": trusted_manifest_digest is not None,
        "verified": not reasons,
        "trusted_manifest_sha256": trusted_manifest_digest,
        "manifest_digest": manifest_digest,
        "extraction_evidence_sha256": manifest["extraction_evidence_sha256"],
        "expected_gate_count": manifest["gate_count"],
        "observed_gate_count": len(observed_gates),
        "expected_gate_set_sha256": manifest["gate_set_sha256"],
        "observed_gate_set_sha256": observed_gate_digest,
        "expected_authority_source_count": manifest["authority_source_count"],
        "observed_authority_source_count": len(observed_sources),
        "expected_authority_source_set_sha256": manifest[
            "authority_source_set_sha256"
        ],
        "observed_authority_source_set_sha256": observed_source_digest,
        "reasons": sorted(set(reasons)),
    }


def _validate_requirement_allowing_authority_scope_mismatch(
    raw, index, sources, evidence, as_of
):
    """Keep core packet-shape checks, but do not abort frozen-root scope drift.

    Relabeling a committed BUYER authority source to CAPABILITY must compile to
    HOLD with PACKAGE_AUTHORITY_SOURCE_SET_MISMATCH rather than raising before
    the independently retained authority set can be compared.
    """
    try:
        return _original_validate_requirement(raw, index, sources, evidence, as_of)
    except QualificationError as exc:
        if ": requirement must bind a BUYER source" not in str(exc):
            raise
        patched_sources = dict(sources)
        for source_id, source in sources.items():
            if source.get("scope") == "BUYER":
                continue
            patched = dict(source)
            patched["scope"] = "BUYER"
            patched_sources[source_id] = patched
        return _original_validate_requirement(
            raw, index, patched_sources, evidence, as_of
        )


def compile_qualification(
    packet,
    *,
    trusted_as_of,
    trusted_completeness=None,
    trusted_completeness_sha256=None,
):
    completeness = None
    try:
        receipt = _original_compile(packet, trusted_as_of=trusted_as_of)
    except QualificationError as exc:
        if ": requirement must bind a BUYER source" not in str(exc):
            raise
        completeness = _assess_completeness(
            packet,
            trusted_as_of=trusted_as_of,
            trusted_completeness=trusted_completeness,
            trusted_completeness_sha256=trusted_completeness_sha256,
        )
        if "PACKAGE_AUTHORITY_SOURCE_SET_MISMATCH" not in completeness["reasons"]:
            raise
        _core._validate_requirement = (
            _validate_requirement_allowing_authority_scope_mismatch
        )
        try:
            receipt = _original_compile(packet, trusted_as_of=trusted_as_of)
        finally:
            _core._validate_requirement = _original_validate_requirement

    package = receipt["package"]

    # A timestamp has negative commercial authority only when the controlling
    # package and deadline source are buyer-official.
    if package["proposal_expired"] and (
        not package["controlling_source_official"]
        or not package["proposal_deadline_source_official"]
    ):
        reasons = []
        if not package["controlling_source_official"]:
            reasons.append("CONTROLLING_PACKAGE_NOT_OFFICIALLY_EVIDENCED")
        if not package["proposal_deadline_source_official"]:
            reasons.append("PROPOSAL_DEADLINE_NOT_OFFICIALLY_EVIDENCED")
        if not package["question_deadline_source_official"]:
            reasons.append("QUESTION_DEADLINE_SOURCE_NOT_OFFICIAL")
        receipt["disposition"] = HOLD
        receipt["reasons"] = sorted(reasons)

    completeness = _assess_completeness(
        packet,
        trusted_as_of=trusted_as_of,
        trusted_completeness=trusted_completeness,
        trusted_completeness_sha256=trusted_completeness_sha256,
    )
    receipt["completeness"] = completeness
    receipt["package"]["completeness_verified"] = completeness["verified"]

    for route_name in ("prime", "team"):
        requirements_ready = receipt[route_name]["ready"]
        receipt[route_name]["requirements_ready"] = requirements_ready
        receipt[route_name]["ready"] = bool(
            requirements_ready and completeness["verified"]
        )

    gate_derived_no_bid = (
        receipt["disposition"] == NO_BID
        and receipt["reasons"] != ["PROPOSAL_DEADLINE_EXPIRED"]
    )
    if not completeness["verified"] and (
        receipt["disposition"] in {PRIME_READY, TEAMING_READY}
        or gate_derived_no_bid
    ):
        receipt["disposition"] = HOLD
        receipt["reasons"] = sorted(
            set(receipt["reasons"] + completeness["reasons"])
        )

    receipt.pop("receipt_digest", None)
    receipt["receipt_digest"] = _core.digest(receipt)
    return receipt


def verify_receipt_against_inputs(
    receipt: Any,
    packet: dict[str, Any],
    *,
    trusted_as_of: str,
    trusted_completeness: Any,
    trusted_completeness_sha256: Any,
) -> bool:
    if not _core.verify_receipt(receipt):
        return False
    try:
        expected = compile_qualification(
            packet,
            trusted_as_of=trusted_as_of,
            trusted_completeness=trusted_completeness,
            trusted_completeness_sha256=trusted_completeness_sha256,
        )
        return _core.canonical_bytes(expected) == _core.canonical_bytes(receipt)
    except QualificationError:
        return False


# Core callers that omit the independently retained trust root fail closed.
_core.compile_qualification = compile_qualification


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Compile opportunity qualification receipts."
    )
    parser.add_argument("packet", help="qualification packet JSON")
    parser.add_argument(
        "--completeness", required=True, help="independent completeness manifest JSON"
    )
    parser.add_argument(
        "--completeness-sha256",
        required=True,
        help="independently retained canonical SHA-256 of the completeness manifest",
    )
    parser.add_argument(
        "--as-of", required=True, help="trusted UTC time, YYYY-MM-DDTHH:MM:SSZ"
    )
    parser.add_argument("--markdown", help="optional Markdown output path")
    args = parser.parse_args()

    with open(args.packet, "r", encoding="utf-8") as handle:
        packet = _core.loads_strict(handle.read())
    with open(args.completeness, "r", encoding="utf-8") as handle:
        completeness = _core.loads_strict(handle.read())
    receipt = compile_qualification(
        packet,
        trusted_as_of=args.as_of,
        trusted_completeness=completeness,
        trusted_completeness_sha256=args.completeness_sha256,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
    if args.markdown:
        with open(args.markdown, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(_core.render_markdown(receipt) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
