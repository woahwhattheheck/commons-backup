#!/usr/bin/env python3
"""Fail-closed gate for the Kentucky AI Workforce Readiness response kit.

Exit codes:
  0 READY   every mandatory gate is RESOLVED by source-owned typed evidence receipts
  1 INVALID manifest/catalog contract is malformed, stale, relabeled, or contradictory
  2 HOLD    manifest is valid but one or more mandatory gates are OPEN/DRAFTED

This validator does not authorize outreach or submission. READY only means that this
specific internal package has source-owned evidence receipts for every required gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 2
CATALOG_SCHEMA_VERSION = 1
TRUSTED_CATALOG_FILENAME = "evidence_catalog.json"
TRUSTED_CATALOG_SHA256 = "e176078ff89b3740bf5db5a9183a2cb0513365da7d74fc13f25425f325128315"

EXPECTED_OPERATION = "R-C08-KY-AI-WORKFORCE-PARTNER-CONTINGENT-RESPONSE-KIT-ZCAP913-20260913"
EXPECTED_BUYER = "South Central Workforce Development Board"
EXPECTED_DEADLINE_LOCAL = "2026-09-18T16:00:00-05:00"
EXPECTED_RFP_INDEX = "https://southcentralworkforce.com/request-for-proposals"
EXPECTED_Q_AND_A = "https://assets.zyrosite.com/mjEQjVPDyGsZw4jM/kentucky-ai-workforce-readiness_rfp-qs-as_2026.08.29_final-nNf7aqGWtJgRqD9J.pdf"

ALLOWED_STATES = {"OPEN", "DRAFTED", "RESOLVED"}
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")

REQUIRED_GATE_IDS = {
    "source_freshness",
    "both_services_and_five_pathways",
    "partner_legal_role_and_consent",
    "minimum_three_year_experience_attribution",
    "three_comparable_references",
    "named_instructor_roster",
    "live_remote_and_kentucky_in_person_capacity",
    "prime_admin_financial_and_federal_funds_capacity",
    "accessibility_plan",
    "privacy_security_and_participant_data_plan",
    "attendance_completion_reporting_and_audit",
    "ip_licensing_and_reviewable_materials",
    "commercial_model_and_approved_prices",
    "subcontractor_disclosure_and_role_matrix",
    "legal_registration_insurance_and_certifications",
    "authorized_signatory_and_submission_owner",
    "final_current_instruction_check",
    "final_package_hash_and_submission_authorization",
}

ALLOWED_KINDS_BY_GATE = {
    "source_freshness": {"official_source_check"},
    "both_services_and_five_pathways": {"curriculum_coverage_receipt"},
    "partner_legal_role_and_consent": {"partner_consent"},
    "minimum_three_year_experience_attribution": {"experience_attribution"},
    "three_comparable_references": {"comparable_reference"},
    "named_instructor_roster": {"instructor_commitment"},
    "live_remote_and_kentucky_in_person_capacity": {"delivery_capacity"},
    "prime_admin_financial_and_federal_funds_capacity": {"admin_financial_capacity"},
    "accessibility_plan": {"accessibility_evidence"},
    "privacy_security_and_participant_data_plan": {"privacy_security_plan"},
    "attendance_completion_reporting_and_audit": {"reporting_audit_plan"},
    "ip_licensing_and_reviewable_materials": {"ip_license_evidence"},
    "commercial_model_and_approved_prices": {"approved_pricing"},
    "subcontractor_disclosure_and_role_matrix": {"subcontractor_role_matrix"},
    "legal_registration_insurance_and_certifications": {"legal_registration_evidence"},
    "authorized_signatory_and_submission_owner": {"signatory_authorization"},
    "final_current_instruction_check": {"final_instruction_check"},
    "final_package_hash_and_submission_authorization": {"final_package_authorization"},
}

MIN_RECEIPTS_BY_GATE = {gate_id: 1 for gate_id in REQUIRED_GATE_IDS}
MIN_RECEIPTS_BY_GATE["three_comparable_references"] = 3


class DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _loads_object(text: str, label: str) -> dict[str, Any]:
    payload = json.loads(text, object_pairs_hook=_unique_object)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be an object")
    return payload


def load_manifest_text(text: str) -> dict[str, Any]:
    return _loads_object(text, "manifest")


def load_catalog_text(text: str) -> dict[str, Any]:
    return _loads_object(text, "catalog")


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    gate_id: str
    kind: str
    source_identity: str
    source_generation: str
    claim: dict[str, Any]
    content_sha256: str


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    state: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    status: str
    gates: tuple[GateResult, ...]

    @property
    def ready(self) -> bool:
        return self.status == "READY"


def _build_trust_generation():
    """Build one private verifier generation with no live module trust leaves."""

    # Capture immutable/built-in primitives and the C-backed SHA constructor at
    # import time. The returned verifier callables never consult module-global
    # hashlib/json/schema/kind helpers after this generation is built.
    type_fn = type
    dict_type = dict
    list_type = list
    str_type = str
    int_type = int
    bool_type = bool
    tuple_type = tuple
    set_type = set
    frozenset_type = frozenset
    sorted_fn = sorted
    enumerate_fn = enumerate
    len_fn = len
    all_fn = all
    next_fn = next
    ord_fn = ord
    value_error = ValueError
    sha256_ctor = hashlib.sha256

    catalog_schema_version = CATALOG_SCHEMA_VERSION
    manifest_schema_version = MANIFEST_SCHEMA_VERSION
    trusted_catalog_sha256 = TRUSTED_CATALOG_SHA256
    allowed_states = frozenset_type(ALLOWED_STATES)
    required_gate_ids = frozenset_type(REQUIRED_GATE_IDS)
    allowed_kinds_by_gate = {
        gate_id: frozenset_type(kinds)
        for gate_id, kinds in ALLOWED_KINDS_BY_GATE.items()
    }
    min_receipts_by_gate = dict(MIN_RECEIPTS_BY_GATE)
    expected_operation = EXPECTED_OPERATION
    expected_buyer = EXPECTED_BUYER
    expected_deadline_local = EXPECTED_DEADLINE_LOCAL
    expected_rfp_index = EXPECTED_RFP_INDEX
    expected_q_and_a = EXPECTED_Q_AND_A
    catalog_id = "ky-ai-workforce-response-kit-evidence"
    receipt_keys = frozenset_type({
        "receipt_id",
        "gate_id",
        "kind",
        "source_identity",
        "source_generation",
        "claim",
        "content_sha256",
    })
    gate_keys = frozenset_type({
        "id", "mandatory", "state", "evidence_note", "evidence_refs",
    })
    receipt_id_fullmatch = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$").fullmatch
    hex64_fullmatch = re.compile(r"^[0-9a-f]{64}$").fullmatch
    date_fullmatch = re.compile(r"\d{4}-\d{2}-\d{2}").fullmatch
    receipt_ctor = Receipt
    gate_result_ctor = GateResult
    evaluation_ctor = Evaluation

    def freeze_json(value: Any, *, path: str = "$") -> Any:
        """Detach one exact plain-JSON generation from caller-owned objects."""
        value_type = type_fn(value)
        if value is None or value_type is str_type or value_type is int_type or value_type is bool_type:
            return value
        if value_type is list_type:
            return [
                freeze_json(item, path=f"{path}[{index}]")
                for index, item in enumerate_fn(value)
            ]
        if value_type is dict_type:
            detached: dict[str, Any] = {}
            for key, item in value.items():
                if type_fn(key) is not str_type:
                    raise value_error(f"{path} object keys must be strings")
                detached[key] = freeze_json(item, path=f"{path}.{key}")
            return detached
        raise value_error(f"{path} contains unsupported JSON type: {value_type.__name__}")

    def quote_json_string(value: str) -> bytes:
        chunks: list[str] = ['"']
        for char in value:
            code = ord_fn(char)
            if char == '"':
                chunks.append('\\"')
            elif char == "\\":
                chunks.append("\\\\")
            elif char == "\b":
                chunks.append("\\b")
            elif char == "\f":
                chunks.append("\\f")
            elif char == "\n":
                chunks.append("\\n")
            elif char == "\r":
                chunks.append("\\r")
            elif char == "\t":
                chunks.append("\\t")
            elif code < 0x20:
                chunks.append(f"\\u{code:04x}")
            elif 0xD800 <= code <= 0xDFFF:
                raise value_error("canonical JSON strings must not contain surrogates")
            else:
                chunks.append(char)
        chunks.append('"')
        return "".join(chunks).encode("utf-8")

    def canonical_json_bytes(value: Any) -> bytes:
        """Canonical JSON for the admitted exact JSON subset, no stdlib JSON calls."""
        value_type = type_fn(value)
        if value is None:
            return b"null"
        if value_type is bool_type:
            return b"true" if value else b"false"
        if value_type is int_type:
            return str_type(value).encode("ascii")
        if value_type is str_type:
            return quote_json_string(value)
        if value_type is list_type:
            return b"[" + b",".join(canonical_json_bytes(item) for item in value) + b"]"
        if value_type is dict_type:
            pieces: list[bytes] = []
            for key in sorted_fn(value):
                if type_fn(key) is not str_type:
                    raise value_error("canonical JSON object keys must be strings")
                pieces.append(
                    quote_json_string(key) + b":" + canonical_json_bytes(value[key])
                )
            return b"{" + b",".join(pieces) + b"}"
        raise value_error(
            f"unsupported canonical JSON type: {value_type.__name__}"
        )

    def sha256_canonical(value: Any) -> str:
        detached = freeze_json(value)
        return sha256_ctor(canonical_json_bytes(detached)).hexdigest()

    def canonical_bytes_public(value: Any) -> bytes:
        detached = freeze_json(value)
        return canonical_json_bytes(detached) + b"\n"

    def index_catalog_frozen(payload: dict[str, Any]) -> dict[str, Receipt]:
        if payload.get("schema_version") != catalog_schema_version:
            raise value_error("catalog schema_version must be exactly 1")
        if payload.get("catalog_id") != catalog_id:
            raise value_error("catalog_id mismatch")
        generation = payload.get("generation")
        if type_fn(generation) is not str_type or not generation.strip():
            raise value_error("catalog generation must be a non-empty string")

        receipts = payload.get("receipts")
        if type_fn(receipts) is not list_type:
            raise value_error("catalog receipts must be a list")

        indexed: dict[str, Receipt] = {}
        digest_owner: dict[str, tuple[str, str]] = {}
        for index, raw in enumerate_fn(receipts):
            if type_fn(raw) is not dict_type:
                raise value_error(f"catalog receipt[{index}] must be an object")
            if set_type(raw) != set_type(receipt_keys):
                raise value_error(f"catalog receipt[{index}] fields mismatch")

            receipt_id = raw["receipt_id"]
            gate_id = raw["gate_id"]
            kind = raw["kind"]
            source_identity = raw["source_identity"]
            source_generation = raw["source_generation"]
            claim = raw["claim"]
            content_sha256 = raw["content_sha256"]

            if (
                type_fn(receipt_id) is not str_type
                or receipt_id_fullmatch(receipt_id) is None
            ):
                raise value_error(f"catalog receipt[{index}] receipt_id invalid")
            if receipt_id in indexed:
                raise value_error(f"duplicate receipt_id: {receipt_id}")
            if gate_id not in required_gate_ids:
                raise value_error(
                    f"receipt {receipt_id} has unknown gate_id: {gate_id}"
                )
            if kind not in allowed_kinds_by_gate[gate_id]:
                raise value_error(
                    f"receipt {receipt_id} kind not allowed for gate {gate_id}"
                )
            if (
                type_fn(source_identity) is not str_type
                or not source_identity.strip()
            ):
                raise value_error(f"receipt {receipt_id} source_identity invalid")
            if (
                type_fn(source_generation) is not str_type
                or not source_generation.strip()
            ):
                raise value_error(f"receipt {receipt_id} source_generation invalid")
            if type_fn(claim) is not dict_type or not claim:
                raise value_error(
                    f"receipt {receipt_id} claim must be a non-empty object"
                )
            if (
                type_fn(content_sha256) is not str_type
                or hex64_fullmatch(content_sha256) is None
            ):
                raise value_error(
                    f"receipt {receipt_id} content_sha256 invalid"
                )

            actual_claim_sha = sha256_canonical(claim)
            if actual_claim_sha != content_sha256:
                raise value_error(f"receipt {receipt_id} claim digest mismatch")

            prior = digest_owner.get(content_sha256)
            if prior is not None:
                raise value_error(
                    "catalog content digest reused/relabelled: "
                    f"{content_sha256} already belongs to {prior[0]}/{prior[1]}"
                )
            digest_owner[content_sha256] = (receipt_id, gate_id)

            indexed[receipt_id] = receipt_ctor(
                receipt_id=receipt_id,
                gate_id=gate_id,
                kind=kind,
                source_identity=source_identity,
                source_generation=source_generation,
                claim=claim,
                content_sha256=content_sha256,
            )
        return indexed

    def index_catalog_public(payload: dict[str, Any]) -> dict[str, Receipt]:
        frozen = freeze_json(payload)
        if type_fn(frozen) is not dict_type:
            raise value_error("catalog root must be an object")
        return index_catalog_frozen(frozen)

    def verify_catalog_root(
        payload: dict[str, Any],
    ) -> dict[str, Receipt]:
        frozen = freeze_json(payload)
        if type_fn(frozen) is not dict_type:
            raise value_error("catalog root must be an object")
        actual = sha256_canonical(frozen)
        if actual != trusted_catalog_sha256:
            raise value_error(
                "evidence catalog generation mismatch: "
                f"{actual} != {trusted_catalog_sha256}"
            )
        return index_catalog_frozen(frozen)

    def require_manifest_identity(payload: dict[str, Any]) -> None:
        exact = (
            ("operation", expected_operation),
            ("buyer", expected_buyer),
            ("deadline_local", expected_deadline_local),
            ("official_rfp_index", expected_rfp_index),
            ("official_q_and_a", expected_q_and_a),
        )
        for field, expected in exact:
            if payload.get(field) != expected:
                raise value_error(f"manifest {field} mismatch")
        checked = payload.get("source_checked_on")
        if (
            type_fn(checked) is not str_type
            or date_fullmatch(checked) is None
        ):
            raise value_error("source_checked_on must be YYYY-MM-DD")

    def evaluate_manifest(
        payload: dict[str, Any],
        catalog_payload: dict[str, Any],
    ) -> Evaluation:
        manifest = freeze_json(payload)
        if type_fn(manifest) is not dict_type:
            raise value_error("manifest root must be an object")
        if manifest.get("schema_version") != manifest_schema_version:
            raise value_error("manifest schema_version must be exactly 2")
        if manifest.get("evidence_catalog_sha256") != trusted_catalog_sha256:
            raise value_error(
                "manifest evidence_catalog_sha256 is stale or untrusted"
            )
        require_manifest_identity(manifest)
        catalog = verify_catalog_root(catalog_payload)

        gates = manifest.get("gates")
        if type_fn(gates) is not list_type:
            raise value_error("gates must be a list")

        seen: set[str] = set_type()
        used_receipts: set[str] = set_type()
        evaluated: list[GateResult] = []
        for index, raw in enumerate_fn(gates):
            if type_fn(raw) is not dict_type:
                raise value_error(f"gate[{index}] must be an object")
            if set_type(raw) != set_type(gate_keys):
                raise value_error(f"gate[{index}] fields mismatch")

            gate_id = raw["id"]
            mandatory = raw["mandatory"]
            state = raw["state"]
            evidence_note = raw["evidence_note"]
            evidence_refs = raw["evidence_refs"]

            if gate_id not in required_gate_ids:
                raise value_error(f"gate[{index}] id invalid: {gate_id!r}")
            if gate_id in seen:
                raise value_error(f"duplicate gate id: {gate_id}")
            seen.add(gate_id)
            if mandatory is not True:
                raise value_error(f"gate {gate_id} must be mandatory=true")
            if state not in allowed_states:
                raise value_error(
                    f"gate {gate_id} has invalid state: {state!r}"
                )
            if type_fn(evidence_note) is not str_type:
                raise value_error(
                    f"gate {gate_id} evidence_note must be a string"
                )
            if (
                type_fn(evidence_refs) is not list_type
                or not all_fn(
                    type_fn(ref) is str_type and ref != ""
                    for ref in evidence_refs
                )
            ):
                raise value_error(
                    f"gate {gate_id} evidence_refs must be a string list"
                )
            if len_fn(set_type(evidence_refs)) != len_fn(evidence_refs):
                raise value_error(
                    f"gate {gate_id} evidence_refs contains duplicates"
                )

            note = evidence_note.strip()
            if state == "OPEN":
                if note or evidence_refs:
                    raise value_error(
                        f"gate {gate_id} OPEN must carry no evidence"
                    )
            elif state == "DRAFTED":
                if not note:
                    raise value_error(
                        f"gate {gate_id} DRAFTED requires a non-authoritative note"
                    )
                if evidence_refs:
                    raise value_error(
                        f"gate {gate_id} DRAFTED must not cite authority receipts"
                    )
            else:
                if not note:
                    raise value_error(
                        f"gate {gate_id} RESOLVED requires a note"
                    )
                minimum = min_receipts_by_gate[gate_id]
                if len_fn(evidence_refs) < minimum:
                    raise value_error(
                        f"gate {gate_id} RESOLVED requires at least "
                        f"{minimum} typed receipt(s)"
                    )
                for receipt_id in evidence_refs:
                    receipt = catalog.get(receipt_id)
                    if receipt is None:
                        raise value_error(
                            f"gate {gate_id} references untrusted receipt: "
                            f"{receipt_id}"
                        )
                    if receipt.gate_id != gate_id:
                        raise value_error(
                            f"cross-gate receipt transplant: {receipt_id} "
                            f"belongs to {receipt.gate_id}, not {gate_id}"
                        )
                    if receipt.kind not in allowed_kinds_by_gate[gate_id]:
                        raise value_error(
                            f"gate {gate_id} receipt kind mismatch: "
                            f"{receipt.kind}"
                        )
                    if receipt_id in used_receipts:
                        raise value_error(
                            f"receipt reused across gates: {receipt_id}"
                        )
                    used_receipts.add(receipt_id)

            evaluated.append(
                gate_result_ctor(
                    gate_id=gate_id,
                    state=state,
                    evidence_refs=tuple_type(evidence_refs),
                )
            )

        missing = required_gate_ids - frozenset_type(seen)
        if missing:
            raise value_error(
                f"missing required gate(s): {', '.join(sorted_fn(missing))}"
            )

        source_gate = next_fn(
            gate
            for gate in evaluated
            if gate.gate_id == "source_freshness"
        )
        if (
            source_gate.state != "RESOLVED"
            or len_fn(source_gate.evidence_refs) != 1
        ):
            raise value_error(
                "source_freshness must have exactly one trusted receipt"
            )
        source_receipt = catalog[source_gate.evidence_refs[0]]
        expected_source_claim = {
            "buyer": expected_buyer,
            "checked_on": manifest["source_checked_on"],
            "deadline_local": expected_deadline_local,
            "required_delivery_modes": ["in_person", "live_remote"],
            "required_services": ["A", "B"],
            "service_a_pathways": [
                "manufacturing",
                "construction",
                "logistics",
                "healthcare",
                "business_operations",
            ],
            "source_url": expected_rfp_index,
        }
        expected_source_claim_sha = sha256_canonical(expected_source_claim)
        if source_receipt.content_sha256 != expected_source_claim_sha:
            raise value_error(
                "source_freshness receipt does not bind "
                "manifest identity/generation"
            )

        status = (
            "READY"
            if all_fn(gate.state == "RESOLVED" for gate in evaluated)
            else "HOLD"
        )
        return evaluation_ctor(
            status=status,
            gates=tuple_type(evaluated),
        )

    return (
        canonical_bytes_public,
        sha256_canonical,
        index_catalog_public,
        verify_catalog_root,
        evaluate_manifest,
    )


(
    _canonical_bytes,
    _sha256_canonical,
    _index_catalog,
    verify_catalog_root,
    evaluate_manifest,
) = _build_trust_generation()
del _build_trust_generation


def _print_human(evaluation: Evaluation, path: Path) -> None:
    blockers = [gate for gate in evaluation.gates if gate.state != "RESOLVED"]
    print(f"KY AI Workforce response kit: {evaluation.status} — {path}")
    print(f"  gates: {len(evaluation.gates)} total / {len(blockers)} unresolved")
    for gate in blockers:
        print(f"  - {gate.gate_id}: {gate.state}")


def _build_main_dispatch():
    # Keep the shipped CLI bound to the same verifier generation even if public
    # module aliases are rebound after import.
    evaluate = evaluate_manifest
    load_manifest = load_manifest_text
    load_catalog = load_catalog_text
    print_human = _print_human
    catalog_filename = TRUSTED_CATALOG_FILENAME
    trusted_catalog_sha256 = TRUSTED_CATALOG_SHA256
    parser_ctor = argparse.ArgumentParser
    path_ctor = Path
    json_dumps = json.dumps
    stderr = sys.stderr
    json_decode_error = json.JSONDecodeError
    duplicate_key_error = DuplicateKeyError
    value_error = ValueError
    os_error = OSError
    unicode_error = UnicodeError

    def main(argv: list[str] | None = None) -> int:
        default_manifest = path_ctor(__file__).with_name("readiness_manifest.json")
        default_catalog = path_ctor(__file__).with_name(catalog_filename)
        parser = parser_ctor(
            description="Fail closed on unresolved SCWDB response gates."
        )
        parser.add_argument("path", nargs="?", type=path_ctor, default=default_manifest)
        parser.add_argument("--catalog", type=path_ctor, default=default_catalog)
        parser.add_argument("--json", action="store_true", dest="as_json")
        args = parser.parse_args(argv)

        try:
            manifest_text = args.path.read_text(encoding="utf-8")
            catalog_text = args.catalog.read_text(encoding="utf-8")
            evaluation = evaluate(
                load_manifest(manifest_text),
                load_catalog(catalog_text),
            )
        except (
            os_error,
            unicode_error,
            json_decode_error,
            duplicate_key_error,
            value_error,
        ) as exc:
            if args.as_json:
                print(json_dumps({
                    "status": "INVALID",
                    "path": str(args.path),
                    "catalog": str(args.catalog),
                    "error": str(exc),
                }, sort_keys=True))
            else:
                print(
                    f"KY AI Workforce response kit: INVALID — {exc}",
                    file=stderr,
                )
            return 1

        if args.as_json:
            print(json_dumps({
                "status": evaluation.status,
                "path": str(args.path),
                "catalog": str(args.catalog),
                "catalog_sha256": trusted_catalog_sha256,
                "gate_count": len(evaluation.gates),
                "unresolved": [
                    {"id": gate.gate_id, "state": gate.state}
                    for gate in evaluation.gates
                    if gate.state != "RESOLVED"
                ],
            }, sort_keys=True))
        else:
            print_human(evaluation, args.path)

        return 0 if evaluation.ready else 2

    return main


main = _build_main_dispatch()
del _build_main_dispatch

if __name__ == "__main__":
    raise SystemExit(main())
