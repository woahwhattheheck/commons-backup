#!/usr/bin/env python3
"""Fail-closed compliance gate for Snohomish County RFP-26-0791BC.

This package does not submit, contact, price, sign, or log into procurement
systems. It verifies that confirmed requirement claims are bound to immutable
reviewed source/requirement identities and reports whether the official packet
is still required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SOURCE_SCHEMA = "snoco-rfp-source-registry/v2"
MATRIX_SCHEMA = "snoco-rfp-compliance-matrix/v1"
RECEIPT_SCHEMA = "snoco-rfp-packet-gate-receipt/v1"
SOLICITATION_ID = "RFP-26-0791BC"

OFFICIAL_AUTHORITIES = frozenset({
    "OFFICIAL_PUBLIC_NOTICE",
    "OFFICIAL_COUNTY_GUIDANCE",
    "OFFICIAL_PORTAL",
})
ALLOWED_AUTHORITIES = OFFICIAL_AUTHORITIES | frozenset({"THIRD_PARTY_MIRROR"})
ALLOWED_STATES = frozenset({"CONFIRMED_OFFICIAL", "PACKET_REQUIRED"})
ALLOWED_CLASSIFICATIONS = frozenset({
    "MANDATORY",
    "SUBMISSION",
    "CONTROL",
    "INFORMATIONAL",
    "SCOREABLE",
    "SCOREABLE_OR_MANDATORY",
})
BOUNDARY_KEYS = frozenset({
    "portal_login_authorized",
    "vendor_registration_authorized",
    "county_contact_authorized",
    "question_submission_authorized",
    "pricing_commitment_authorized",
    "signature_authorized",
    "proposal_submission_authorized",
    "award_claim_authorized",
    "recognized_revenue",
})


class GateError(ValueError):
    pass


class DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _make_authority_api():
    """Build the authority API around closure-held reviewed identities.

    The old implementation exposed mutable TRUSTED_* dictionaries and reread
    them on every validation call. Ordinary same-process code could mutate
    those maps, then present matching forged registry/matrix rows and mint a
    new CONFIRMED_OFFICIAL claim. The reviewed identities below are closure
    state, not module-level authority knobs.
    """
    json_dumps = json.dumps
    sha256_impl = hashlib.sha256
    gate_error = GateError

    source_schema = "snoco-rfp-source-registry/v2"
    matrix_schema = "snoco-rfp-compliance-matrix/v1"
    receipt_schema = "snoco-rfp-packet-gate-receipt/v1"
    solicitation_id = "RFP-26-0791BC"

    official_authorities = frozenset({
        "OFFICIAL_PUBLIC_NOTICE",
        "OFFICIAL_COUNTY_GUIDANCE",
        "OFFICIAL_PORTAL",
    })
    allowed_authorities = official_authorities | frozenset({"THIRD_PARTY_MIRROR"})
    allowed_states = frozenset({"CONFIRMED_OFFICIAL", "PACKET_REQUIRED"})
    allowed_classifications = frozenset({
        "MANDATORY",
        "SUBMISSION",
        "CONTROL",
        "INFORMATIONAL",
        "SCOREABLE",
        "SCOREABLE_OR_MANDATORY",
    })
    boundary_keys = frozenset({
        "portal_login_authorized",
        "vendor_registration_authorized",
        "county_contact_authorized",
        "question_submission_authorized",
        "pricing_commitment_authorized",
        "signature_authorized",
        "proposal_submission_authorized",
        "award_claim_authorized",
        "recognized_revenue",
    })

    # Canonical SHA-256 identities of the exact five reviewed official source
    # records. These are generated from canonical JSON (sorted keys, compact
    # separators, UTF-8) and are intentionally not module-level mutable maps.
    trusted_source_hashes = dict((
        ("snoco_legal_notice", "96d526893012c3957171d2f7b1d076a5614c2057dfe820a2371112e0d9ced8a8"),
        ("snoco_supplier_info", "34873f2c26415afb522f2349db6af6d8ef2767520bda3bfdc9a4adac11a386e4"),
        ("snoco_purchasing_portal_page", "72baa969797c3d3397988667e749f65c2a46cbb4448a65239b269ab324ee99f6"),
        ("snoco_procureware_guide", "225721f9f126f68744198f977971c139f6230e5fb0de404de3a7773119abe6d5"),
        ("procureware_public_portal", "7243fe3e7f6ef5aeca47d60e935be394adaca884f9fb005239fa584214c20782"),
    ))

    # Canonical SHA-256 identities of every currently CONFIRMED_OFFICIAL
    # requirement. Any text/classification/state/citation drift changes the
    # digest and therefore cannot be promoted by caller process state.
    trusted_requirement_hashes = dict((
        ("identity", "5f47592aa24b3b5dae541c4e253ffbaa529f2758e06f73ce0d0b4d4bf7248607"),
        ("proposal_due", "e8f9dba31710df4e24f6d5316e7efbeaed4c19aca5822ce1663bc5aad364b2f4"),
        ("late_submittals", "319288b55eacf70805578f0ccb19a77065f4b4fafc64cf90df5ec9727286d531"),
        ("electronic_preferred", "3a6273ba59cae9277b7b3fcd6c82a5ee1f1851c0dec511f7c692b8b2c7fb7985"),
        ("electronic_signature", "43afae8c790b9a349f17b3ab1b25479bcac0292eddf8414a3aa33a1554721168"),
        ("email_subject", "5aee684b8115250cf4b5e92886a8892d995358ec46ed85c252b28a5e793c3587"),
        ("hardcopy_signature", "7005fe63cf0b57e73e4818e76d38b86f2e44fb29bb12cff472fd81f075a779c3"),
        ("hand_delivery_location", "8ed9e98b27befbf06db6538b074cfcc769c747afcdd6bbbe18ca4617b25e8099"),
        ("official_document_source", "b21537311f53558290b86714af7cfb8dc9f21b68a4657bec4333ea864559b38f"),
        ("clarification_channel_general", "010d1711594bb8aa1a1df9a6c687ac40ed48f4f6f384cf00eef2df5fe31b2fee"),
    ))

    # Canonical SHA-256 identities of the complete currently-known packet gap
    # inventory. These rows are authority too: allowing callers to delete,
    # reclassify, or rewrite them would understate the mandatory/scoreable work
    # still blocked on official packet retrieval while leaving a valid HOLD
    # receipt. Keep the reviewed gap catalog closure-held for the same reason as
    # the confirmed and official-source identities above.
    trusted_packet_requirement_hashes = dict((
        ("clarification_deadline", "30549e9fdfab89f141b0712c84c80a040539307b8c6bceaf7e780a45a29cd451"),
        ("submission_email", "9ebd25d98db6c16e7cb97d5b3b66571c6bee3757a3e5523e7b9beb49e753da1a"),
        ("required_forms", "7f5cccae5f264f680a2b6b2ec00c8a91a24e570e4fc5f69247a51926ebaad70b"),
        ("minimum_qualifications", "3e3eea0ee373256b940e10b3e10eede82d8ccd170c262eade2dc60dde59f55a3"),
        ("references", "e3685d733dcfc9b264b902f97b82556664e2b0a3d91429886ff72071c8ac4771"),
        ("evaluation_scoring", "104ba58f7533a7083938b1955d91c46b7b903a6318f42905dfaa04e07a82926c"),
        ("technical_requirements", "551a6c9f79a0eb5097fdce0c8c7445d7ea3186e940d973403a48d04b5be39618"),
        ("security_privacy", "114200c31bd4de4c02fbe9f6042b0e127aecffdeeeadc746e4cb812dd3778bb2"),
        ("pricing_form", "9ad820e65bd797ed2923006e3b1d87d25b01691c8296c98f825465dda8d3cd2a"),
        ("insurance", "0771d1eba719f7d70cacef2daaa1121954f7f7fe54f9df5c9495266979be35ea"),
        ("contract_terms", "0d0dfb4ddb3fc73f0e213c96df4c2b87a1740b47c624f52b40a8b8f48e844efd"),
        ("teaming_subcontract", "a750b53527ca7bbe11ad68e1eba415829ca5c914cf2c5ceddebab9dec4f7fb8d"),
        ("proposal_format", "f9d99760418d127ee0a5726da63da34632160a48b4b42594f123399c658a1b06"),
        ("addenda_acknowledgement", "24c6f94e572ffaf4d318d879d93e986ba04b03c82635fce192ad9cbc9e04ff8c"),
    ))

    def canonical(value: Any) -> bytes:
        return json_dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def digest(value: Any) -> str:
        return sha256_impl(canonical(value)).hexdigest()

    def exact_keys(obj: Any, expected: frozenset[str] | set[str], label: str) -> None:
        if not isinstance(obj, dict):
            raise gate_error(f"{label} must be an object")
        actual = set(obj)
        wanted = set(expected)
        if actual != wanted:
            missing = sorted(wanted - actual)
            extra = sorted(actual - wanted)
            raise gate_error(f"{label} keys mismatch: missing={missing} extra={extra}")

    def bounded_text(value: Any, label: str, maximum: int = 1000) -> str:
        if not isinstance(value, str):
            raise gate_error(f"{label} must be text")
        clean = " ".join(value.split())
        if not clean or len(clean) > maximum or any(ord(c) < 32 for c in clean):
            raise gate_error(f"{label} must be bounded printable text")
        return clean

    def bounded_unique_text_list(value: Any, label: str, maximum: int = 120) -> list[str]:
        if not isinstance(value, list):
            raise gate_error(f"{label} must be a list")
        normalized = [
            bounded_text(item, f"{label}[{index}]", maximum)
            for index, item in enumerate(value)
        ]
        if len(set(normalized)) != len(normalized):
            raise gate_error(f"{label} must not contain duplicates")
        return normalized

    def validate_official_source(source: dict[str, Any], sid: str) -> None:
        expected_digest = trusted_source_hashes.get(sid)
        if expected_digest is None:
            raise gate_error(f"untrusted official source id: {sid}")
        if digest(source) != expected_digest:
            raise gate_error(f"official source identity drift: {sid}")

    def validate_sources_impl(registry: Any) -> dict[str, dict[str, Any]]:
        exact_keys(
            registry,
            {"schema", "solicitation_id", "title", "retrieved_at", "sources"},
            "source registry",
        )
        if registry["schema"] != source_schema or registry["solicitation_id"] != solicitation_id:
            raise gate_error("wrong source registry identity")
        bounded_text(registry["title"], "title", 200)
        if not isinstance(registry["retrieved_at"], str) or not registry["retrieved_at"].endswith("Z"):
            raise gate_error("retrieved_at must be a UTC string")
        if not isinstance(registry["sources"], list) or not registry["sources"]:
            raise gate_error("sources must be a non-empty list")

        by_id: dict[str, dict[str, Any]] = {}
        for index, source in enumerate(registry["sources"]):
            exact_keys(
                source,
                {
                    "id",
                    "authority",
                    "url",
                    "assertable",
                    "raw_bytes_sha256",
                    "raw_hash_status",
                    "supports_requirement_ids",
                    "facts",
                },
                f"source[{index}]",
            )
            sid = bounded_text(source["id"], f"source[{index}].id", 120)
            if sid in by_id:
                raise gate_error(f"duplicate source id: {sid}")
            authority = source["authority"]
            if authority not in allowed_authorities:
                raise gate_error(f"unsupported authority: {authority}")
            if not isinstance(source["url"], str) or not source["url"].startswith("https://"):
                raise gate_error(f"source {sid} must use https")

            if authority in official_authorities:
                validate_official_source(source, sid)
            elif source["assertable"] is not False:
                raise gate_error(f"third-party source {sid} must be non-assertable")

            raw_digest = source["raw_bytes_sha256"]
            if raw_digest is not None and (
                not isinstance(raw_digest, str)
                or len(raw_digest) != 64
                or any(c not in "0123456789abcdef" for c in raw_digest)
            ):
                raise gate_error(f"source {sid} raw_bytes_sha256 is invalid")
            bounded_text(source["raw_hash_status"], f"source {sid} hash status", 120)
            supports = bounded_unique_text_list(
                source["supports_requirement_ids"],
                f"source {sid} supports_requirement_ids",
            )
            if not supports:
                raise gate_error(f"source {sid} must bind at least one requirement id")
            if not isinstance(source["facts"], list) or not source["facts"]:
                raise gate_error(f"source {sid} needs at least one fact")
            for fact_index, fact in enumerate(source["facts"]):
                bounded_text(fact, f"source {sid} fact[{fact_index}]", 600)
            by_id[sid] = source

        missing_official = sorted(set(trusted_source_hashes) - set(by_id))
        if missing_official:
            raise gate_error(f"trusted official source(s) missing: {missing_official}")
        return by_id

    def validate_matrix_impl(matrix: Any, sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        exact_keys(
            matrix,
            {"schema", "solicitation_id", "packet_state", "requirements", "boundaries"},
            "matrix",
        )
        if matrix["schema"] != matrix_schema or matrix["solicitation_id"] != solicitation_id:
            raise gate_error("wrong matrix identity")
        if matrix["packet_state"] != "LOGIN_REQUIRED_NOT_RETRIEVED":
            raise gate_error("packet_state must fail closed until the official packet is actually retrieved")
        if not isinstance(matrix["requirements"], list) or not matrix["requirements"]:
            raise gate_error("requirements must be a non-empty list")
        if not isinstance(sources, dict):
            raise gate_error("sources must be a validated source mapping")

        ids: set[str] = set()
        normalized: list[dict[str, Any]] = []
        confirmed_ids: set[str] = set()
        packet_required_ids: set[str] = set()

        for index, req in enumerate(matrix["requirements"]):
            exact_keys(
                req,
                {"id", "classification", "state", "source_ids", "requirement"},
                f"requirement[{index}]",
            )
            rid = bounded_text(req["id"], f"requirement[{index}].id", 120)
            if rid in ids:
                raise gate_error(f"duplicate requirement id: {rid}")
            ids.add(rid)
            if req["classification"] not in allowed_classifications:
                raise gate_error(f"unsupported classification for {rid}")
            if req["state"] not in allowed_states:
                raise gate_error(f"unsupported state for {rid}")
            if not isinstance(req["source_ids"], list):
                raise gate_error(f"source_ids for {rid} must be a list")
            if len(set(req["source_ids"])) != len(req["source_ids"]):
                raise gate_error(f"duplicate source ids for {rid}")

            cited: list[dict[str, Any]] = []
            for sid in req["source_ids"]:
                if sid not in sources:
                    raise gate_error(f"unknown source {sid} for {rid}")
                source = sources[sid]
                if not isinstance(source, dict):
                    raise gate_error(f"source {sid} must be an object")
                if rid not in source.get("supports_requirement_ids", []):
                    raise gate_error(f"source {sid} does not support requirement {rid}")
                cited.append(source)
            bounded_text(req["requirement"], f"requirement {rid}", 1200)

            if req["state"] == "CONFIRMED_OFFICIAL":
                expected_digest = trusted_requirement_hashes.get(rid)
                if expected_digest is None:
                    raise gate_error(f"untrusted confirmed requirement id: {rid}")
                if digest(req) != expected_digest:
                    raise gate_error(f"confirmed requirement identity drift: {rid}")
                if not cited:
                    raise gate_error(f"confirmed requirement {rid} must cite official evidence")
                for source in cited:
                    sid = source.get("id")
                    if (
                        not isinstance(sid, str)
                        or source.get("authority") not in official_authorities
                        or source.get("assertable") is not True
                    ):
                        raise gate_error(f"confirmed requirement {rid} cites non-official authority")
                    # Re-pin source identity here as well so direct callers of
                    # validate_matrix cannot bypass validate_sources.
                    validate_official_source(source, sid)
                confirmed_ids.add(rid)
            elif req["state"] == "PACKET_REQUIRED":
                expected_digest = trusted_packet_requirement_hashes.get(rid)
                if expected_digest is None:
                    raise gate_error(f"untrusted packet-required requirement id: {rid}")
                if digest(req) != expected_digest:
                    raise gate_error(f"packet-gap row drift: {rid}")
                packet_required_ids.add(rid)
            normalized.append(req)

        expected_confirmed_ids = set(trusted_requirement_hashes)
        if confirmed_ids != expected_confirmed_ids:
            missing = sorted(expected_confirmed_ids - confirmed_ids)
            extra = sorted(confirmed_ids - expected_confirmed_ids)
            raise gate_error(f"confirmed requirement set drift: missing={missing} extra={extra}")

        expected_packet_required_ids = set(trusted_packet_requirement_hashes)
        if packet_required_ids != expected_packet_required_ids:
            missing = sorted(expected_packet_required_ids - packet_required_ids)
            extra = sorted(packet_required_ids - expected_packet_required_ids)
            raise gate_error(f"packet-required requirement set drift: missing={missing} extra={extra}")

        exact_keys(matrix["boundaries"], boundary_keys, "boundaries")
        for key in boundary_keys:
            if matrix["boundaries"][key] is not False:
                raise gate_error(f"authority boundary escalated: {key}")
        return normalized

    def build_receipt_impl(registry: Any, matrix: Any) -> dict[str, Any]:
        # These are closure references, not module-global lookups.
        sources = validate_sources_impl(registry)
        requirements = validate_matrix_impl(matrix, sources)
        confirmed = [req["id"] for req in requirements if req["state"] == "CONFIRMED_OFFICIAL"]
        packet_required = [req["id"] for req in requirements if req["state"] == "PACKET_REQUIRED"]
        scoreable_packet_required = [
            req["id"]
            for req in requirements
            if req["state"] == "PACKET_REQUIRED"
            and req["classification"] in {"SCOREABLE", "SCOREABLE_OR_MANDATORY"}
        ]
        mandatory_packet_required = [
            req["id"]
            for req in requirements
            if req["state"] == "PACKET_REQUIRED"
            and req["classification"] in {"MANDATORY", "SCOREABLE_OR_MANDATORY"}
        ]
        if not packet_required:
            raise gate_error("this receipt must not claim packet completeness without official packet ingestion")

        core = {
            "schema": receipt_schema,
            "solicitation_id": solicitation_id,
            "source_registry_sha256": digest(registry),
            "matrix_sha256": digest(matrix),
            "official_source_count": sum(
                source["authority"] in official_authorities for source in sources.values()
            ),
            "mirror_source_count": sum(
                source["authority"] == "THIRD_PARTY_MIRROR" for source in sources.values()
            ),
            "confirmed_official_ids": confirmed,
            "packet_required_ids": packet_required,
            "mandatory_packet_required_ids": mandatory_packet_required,
            "scoreable_packet_required_ids": scoreable_packet_required,
            "decision": "HOLD_PACKET_REQUIRED",
            "state": "EVIDENCE_MATRIX_READY_PACKET_BLOCKED",
            "authorities": dict(matrix["boundaries"]),
        }
        return {**core, "receipt_sha256": digest(core)}

    def verify_receipt_impl(receipt: Any, registry: Any, matrix: Any) -> bool:
        try:
            rebuilt = build_receipt_impl(registry, matrix)
        except (gate_error, TypeError, ValueError):
            return False
        return receipt == rebuilt

    return (
        validate_sources_impl,
        validate_matrix_impl,
        build_receipt_impl,
        verify_receipt_impl,
    )


validate_sources, validate_matrix, build_receipt, verify_receipt = _make_authority_api()
del _make_authority_api


def _load(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, DuplicateKeyError) as exc:
        raise GateError(f"invalid JSON in {path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=Path(__file__).with_name("sources.json"))
    parser.add_argument("--matrix", type=Path, default=Path(__file__).with_name("matrix.json"))
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    registry = _load(args.sources)
    matrix = _load(args.matrix)
    receipt = build_receipt(registry, matrix)
    if args.verify:
        if args.receipt is None:
            raise SystemExit("--verify requires --receipt")
        supplied = _load(args.receipt)
        ok = verify_receipt(supplied, registry, matrix)
        print(json.dumps({"ok": ok}, sort_keys=True))
        return 0 if ok else 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
