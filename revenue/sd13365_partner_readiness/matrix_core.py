#!/usr/bin/env python3
"""Fail-closed public-evidence matrix for San Diego County RFP 13365.

This module does not determine vendor compliance. It validates that a public-
evidence assessment is complete, conservatively classified, source-linked, and
stripped of contact, bid, production, or compliance-certification authority.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
import gzip
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

SCHEMA = 1
OPERATION = "R-SD13365-PROBATION-AI-TEAMING-ZCAS913455-20260913"
STRONGEST_STATE = "PUBLIC_EVIDENCE_GAPS_DOCUMENTED"
REVIEWED_SOURCE_MATRIX_SHA256 = "e6e857e1df33a6b6d486252fd1e0f1f243fdf0818b48ebfe6a80525e5dc19f42"
REVIEWED_PAYLOAD_NAME = "requirements.json.gz.b64"
MAX_REVIEWED_ENCODED_BYTES = 32_768
MAX_REVIEWED_COMPRESSED_BYTES = 16_384
MAX_REVIEWED_MATRIX_BYTES = 65_536
EXPECTED_REQUIREMENTS = (
    "fips-140-3",
    "sso-saml-oauth",
    "audit-retention-seven-years",
    "intune-mobile-deployment",
    "us-only-support",
    "wcag-2-1-aa-vpat",
    "annual-penetration-test",
    "backup-retention-180-days",
    "incident-response-24x7",
    "ai-bom",
    "artifact-cryptographic-signing",
    "prompt-injection-defenses",
    "data-poisoning-anomaly-detection",
)
REVIEWED_CLASSIFICATIONS = {requirement_id: "UNKNOWN" for requirement_id in EXPECTED_REQUIREMENTS}
STATUSES = {"PASS", "UNKNOWN", "RED"}
RELATIONSHIPS = {"direct_support", "adjacent_only", "direct_contradiction"}
SOURCE_KINDS = {
    "official_procurement_record",
    "official_rfp",
    "indexed_official_attachment",
}
ALLOWED_HOSTS = {
    "sdbuynet.sandiegocounty.gov",
    "govtribe.com",
    "cognisen.com",
    "sanmateocounty.legistar.com",
}
FALSE_AUTHORITY_FIELDS = {
    "contact_vendor_authorized",
    "contact_county_authorized",
    "bid_submission_authorized",
    "compliance_certification_authorized",
    "production_access_authorized",
    "cji_phi_access_authorized",
    "pricing_authorized",
    "contract_signature_authorized",
}
FORBIDDEN_WEDGE_ACTIONS = {
    "contact_vendor",
    "contact_county",
    "submit_bid",
    "certify_compliance",
    "access_production",
    "access_cji_phi",
    "set_pricing",
    "sign_contract",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class MatrixError(ValueError):
    """Raised when evidence or authority data fail closed."""


def _reject_constant(value: str) -> None:
    raise MatrixError(f"non-finite JSON number is forbidden: {value}")


def _reject_duplicate_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MatrixError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads_strict(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except MatrixError:
        raise
    except (TypeError, json.JSONDecodeError) as exc:
        raise MatrixError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise MatrixError("matrix root must be an object")
    return value


def load_matrix(path: Path) -> dict[str, Any]:
    try:
        return loads_strict(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MatrixError(f"cannot read matrix: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalized_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    """Return a semantic canonical form for set-like matrix collections."""
    normalized = copy.deepcopy(matrix)
    requirements = normalized.get("requirements")
    if isinstance(requirements, list):
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            for field in ("county_sources", "public_evidence"):
                sources = requirement.get(field)
                if isinstance(sources, list):
                    sources.sort(
                        key=lambda item: (
                            str(item.get("url", "")) if isinstance(item, dict) else "",
                            str(item.get("title", "")) if isinstance(item, dict) else "",
                        )
                    )
        requirements.sort(
            key=lambda item: str(item.get("id", "")) if isinstance(item, dict) else ""
        )
    wedge = normalized.get("subcontract_wedge")
    if isinstance(wedge, dict):
        components = wedge.get("components")
        if isinstance(components, list):
            components.sort(
                key=lambda item: str(item.get("id", "")) if isinstance(item, dict) else ""
            )
        forbidden = wedge.get("forbidden_actions")
        if isinstance(forbidden, list):
            forbidden.sort(key=str)
    return normalized


def _load_reviewed_source_matrix() -> dict[str, Any]:
    """Load the exact reviewed source generation without trusting caller bytes."""
    payload_path = Path(__file__).resolve().parent / REVIEWED_PAYLOAD_NAME
    try:
        encoded = payload_path.read_bytes().strip()
    except OSError as exc:
        raise MatrixError(f"cannot read reviewed source payload: {exc}") from exc
    if len(encoded) > MAX_REVIEWED_ENCODED_BYTES:
        raise MatrixError("reviewed source payload exceeds encoded size bound")
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MatrixError("reviewed source payload is not canonical base64") from exc
    if len(compressed) > MAX_REVIEWED_COMPRESSED_BYTES:
        raise MatrixError("reviewed source payload exceeds compressed size bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as handle:
            raw = handle.read(MAX_REVIEWED_MATRIX_BYTES + 1)
    except (EOFError, OSError) as exc:
        raise MatrixError("reviewed source payload is not a valid gzip stream") from exc
    if len(raw) > MAX_REVIEWED_MATRIX_BYTES:
        raise MatrixError("reviewed source matrix exceeds decoded size bound")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != REVIEWED_SOURCE_MATRIX_SHA256:
        raise MatrixError(
            "reviewed source matrix SHA-256 mismatch: "
            f"expected {REVIEWED_SOURCE_MATRIX_SHA256}, got {digest}"
        )
    try:
        return loads_strict(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise MatrixError("reviewed source matrix is not UTF-8") from exc


def _require_type(value: Any, expected: type, path: str) -> Any:
    if expected is int and isinstance(value, bool):
        raise MatrixError(f"{path} must be int, not bool")
    if not isinstance(value, expected):
        raise MatrixError(f"{path} must be {expected.__name__}")
    return value


def _require_string(value: Any, path: str, *, min_length: int = 1) -> str:
    value = _require_type(value, str, path)
    if len(value.strip()) < min_length:
        raise MatrixError(f"{path} must not be blank")
    if "\x00" in value:
        raise MatrixError(f"{path} contains NUL")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise MatrixError(f"{path} keys mismatch; missing={missing}, extra={extra}")


def _validate_iso_date(value: Any, path: str) -> str:
    value = _require_string(value, path)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise MatrixError(f"{path} must be YYYY-MM-DD") from exc
    return value


def _validate_iso_datetime(value: Any, path: str) -> str:
    value = _require_string(value, path)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MatrixError(f"{path} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MatrixError(f"{path} must include an offset")
    return value


def _validate_url(value: Any, path: str) -> str:
    value = _require_string(value, path)
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise MatrixError(f"{path} must use https")
    if not parsed.hostname or parsed.hostname.lower() not in ALLOWED_HOSTS:
        raise MatrixError(f"{path} host is not allowlisted")
    if parsed.username is not None or parsed.password is not None:
        raise MatrixError(f"{path} must not contain credentials")
    if parsed.fragment:
        raise MatrixError(f"{path} must not contain a fragment")
    return value


def _validate_source(source: Any, path: str, *, county: bool) -> dict[str, Any]:
    source = _require_type(source, dict, path)
    expected = {"url", "publisher", "title", "observed_on", "claim"}
    if county:
        expected.add("kind")
    else:
        expected.add("relationship")
    _require_exact_keys(source, expected, path)
    _validate_url(source["url"], f"{path}.url")
    _require_string(source["publisher"], f"{path}.publisher")
    _require_string(source["title"], f"{path}.title")
    _validate_iso_date(source["observed_on"], f"{path}.observed_on")
    _require_string(source["claim"], f"{path}.claim", min_length=20)
    if county:
        kind = _require_string(source["kind"], f"{path}.kind")
        if kind not in SOURCE_KINDS:
            raise MatrixError(f"{path}.kind is unsupported")
    else:
        relationship = _require_string(source["relationship"], f"{path}.relationship")
        if relationship not in RELATIONSHIPS:
            raise MatrixError(f"{path}.relationship is unsupported")
    return source


def _validate_requirement(requirement: Any, index: int) -> dict[str, Any]:
    path = f"requirements[{index}]"
    requirement = _require_type(requirement, dict, path)
    _require_exact_keys(
        requirement,
        {
            "id",
            "name",
            "county_requirement",
            "county_sources",
            "public_evidence",
            "status",
            "rationale",
            "closure_artifact",
        },
        path,
    )
    requirement_id = _require_string(requirement["id"], f"{path}.id")
    if not _ID_RE.fullmatch(requirement_id):
        raise MatrixError(f"{path}.id is not canonical")
    _require_string(requirement["name"], f"{path}.name")
    _require_string(requirement["county_requirement"], f"{path}.county_requirement", min_length=20)
    county_sources = _require_type(requirement["county_sources"], list, f"{path}.county_sources")
    if not county_sources:
        raise MatrixError(f"{path}.county_sources must not be empty")
    validated_county = [
        _validate_source(source, f"{path}.county_sources[{source_index}]", county=True)
        for source_index, source in enumerate(county_sources)
    ]
    if not any(
        urlsplit(source["url"]).hostname == "sdbuynet.sandiegocounty.gov"
        and source["kind"] in {"official_procurement_record", "official_rfp"}
        for source in validated_county
    ):
        raise MatrixError(f"{path} lacks an official County of San Diego source")

    public_evidence = _require_type(requirement["public_evidence"], list, f"{path}.public_evidence")
    validated_evidence = [
        _validate_source(source, f"{path}.public_evidence[{source_index}]", county=False)
        for source_index, source in enumerate(public_evidence)
    ]
    status = _require_string(requirement["status"], f"{path}.status")
    if status not in STATUSES:
        raise MatrixError(f"{path}.status is unsupported")
    relationships = {source["relationship"] for source in validated_evidence}
    if status == "PASS":
        if "direct_support" not in relationships:
            raise MatrixError(f"{path}: PASS requires direct_support evidence")
        if "direct_contradiction" in relationships:
            raise MatrixError(f"{path}: PASS cannot coexist with direct contradiction")
    elif status == "RED":
        if "direct_contradiction" not in relationships:
            raise MatrixError(f"{path}: RED requires direct_contradiction evidence")
        if "direct_support" in relationships:
            raise MatrixError(f"{path}: RED cannot coexist with direct support")
    else:
        if relationships & {"direct_support", "direct_contradiction"}:
            raise MatrixError(f"{path}: UNKNOWN may contain only adjacent evidence")
    _require_string(requirement["rationale"], f"{path}.rationale", min_length=30)
    _require_string(requirement["closure_artifact"], f"{path}.closure_artifact", min_length=20)
    return requirement


def validate_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    _require_exact_keys(
        matrix,
        {
            "schema",
            "operation",
            "evidence_cutoff",
            "classification_policy",
            "opportunity",
            "requirements",
            "subcontract_wedge",
            "authority",
        },
        "root",
    )
    if _require_type(matrix["schema"], int, "schema") != SCHEMA:
        raise MatrixError("unsupported schema")
    if _require_string(matrix["operation"], "operation") != OPERATION:
        raise MatrixError("operation mismatch")
    _validate_iso_date(matrix["evidence_cutoff"], "evidence_cutoff")

    policy = _require_type(matrix["classification_policy"], dict, "classification_policy")
    _require_exact_keys(policy, {"PASS", "UNKNOWN", "RED", "scope"}, "classification_policy")
    for status in ("PASS", "UNKNOWN", "RED"):
        _require_string(policy[status], f"classification_policy.{status}", min_length=20)
    if _require_string(policy["scope"], "classification_policy.scope") != "public_evidence_only":
        raise MatrixError("classification scope must be public_evidence_only")

    opportunity = _require_type(matrix["opportunity"], dict, "opportunity")
    _require_exact_keys(
        opportunity,
        {"solicitation_id", "portal_id", "buyer", "title", "due_at", "official_url"},
        "opportunity",
    )
    if _require_string(opportunity["solicitation_id"], "opportunity.solicitation_id") != "RFP 13365":
        raise MatrixError("solicitation id mismatch")
    if _require_string(opportunity["portal_id"], "opportunity.portal_id") != "BPM013365":
        raise MatrixError("portal id mismatch")
    _require_string(opportunity["buyer"], "opportunity.buyer")
    _require_string(opportunity["title"], "opportunity.title")
    _validate_iso_datetime(opportunity["due_at"], "opportunity.due_at")
    official_url = _validate_url(opportunity["official_url"], "opportunity.official_url")
    if urlsplit(official_url).hostname != "sdbuynet.sandiegocounty.gov":
        raise MatrixError("opportunity URL must be official BuyNet")

    requirements = _require_type(matrix["requirements"], list, "requirements")
    validated = [_validate_requirement(value, index) for index, value in enumerate(requirements)]
    ids = [requirement["id"] for requirement in validated]
    if len(ids) != len(set(ids)):
        raise MatrixError("duplicate requirement id")
    if set(ids) != set(EXPECTED_REQUIREMENTS):
        raise MatrixError(
            f"requirement set mismatch; missing={sorted(set(EXPECTED_REQUIREMENTS) - set(ids))}, "
            f"extra={sorted(set(ids) - set(EXPECTED_REQUIREMENTS))}"
        )
    observed_classifications = {item["id"]: item["status"] for item in validated}
    if observed_classifications != REVIEWED_CLASSIFICATIONS:
        changed = sorted(
            requirement_id
            for requirement_id in EXPECTED_REQUIREMENTS
            if observed_classifications.get(requirement_id) != REVIEWED_CLASSIFICATIONS[requirement_id]
        )
        raise MatrixError(
            "classification differs from reviewed source generation "
            f"{REVIEWED_SOURCE_MATRIX_SHA256}; changed={changed}"
        )

    wedge = _require_type(matrix["subcontract_wedge"], dict, "subcontract_wedge")
    _require_exact_keys(wedge, {"name", "components", "forbidden_actions"}, "subcontract_wedge")
    _require_string(wedge["name"], "subcontract_wedge.name")
    components = _require_type(wedge["components"], list, "subcontract_wedge.components")
    if not components:
        raise MatrixError("subcontract_wedge.components must not be empty")
    component_ids: set[str] = set()
    for index, component in enumerate(components):
        path = f"subcontract_wedge.components[{index}]"
        component = _require_type(component, dict, path)
        _require_exact_keys(component, {"id", "deliverable", "boundary"}, path)
        component_id = _require_string(component["id"], f"{path}.id")
        if not _ID_RE.fullmatch(component_id) or component_id in component_ids:
            raise MatrixError(f"{path}.id is duplicate or noncanonical")
        component_ids.add(component_id)
        _require_string(component["deliverable"], f"{path}.deliverable", min_length=25)
        _require_string(component["boundary"], f"{path}.boundary", min_length=25)

    forbidden = _require_type(wedge["forbidden_actions"], list, "subcontract_wedge.forbidden_actions")
    if set(forbidden) != FORBIDDEN_WEDGE_ACTIONS or len(forbidden) != len(FORBIDDEN_WEDGE_ACTIONS):
        raise MatrixError("subcontract_wedge.forbidden_actions must exactly preserve the safety boundary")

    authority = _require_type(matrix["authority"], dict, "authority")
    _require_exact_keys(authority, FALSE_AUTHORITY_FIELDS, "authority")
    for field in sorted(FALSE_AUTHORITY_FIELDS):
        if authority[field] is not False:
            raise MatrixError(f"authority.{field} must be false")

    reviewed = _load_reviewed_source_matrix()
    if normalized_matrix(matrix) != normalized_matrix(reviewed):
        raise MatrixError(
            "matrix differs from reviewed source generation "
            f"{REVIEWED_SOURCE_MATRIX_SHA256}"
        )
    return matrix


def build_receipt(matrix: dict[str, Any]) -> dict[str, Any]:
    validate_matrix(matrix)
    ordered_requirements = sorted(matrix["requirements"], key=lambda item: item["id"])
    counts = {status: 0 for status in sorted(STATUSES)}
    for requirement in ordered_requirements:
        counts[requirement["status"]] += 1
    receipt = {
        "schema": SCHEMA,
        "operation": OPERATION,
        "opportunity": {
            "solicitation_id": matrix["opportunity"]["solicitation_id"],
            "portal_id": matrix["opportunity"]["portal_id"],
            "due_at": matrix["opportunity"]["due_at"],
        },
        "evidence_cutoff": matrix["evidence_cutoff"],
        "classification_scope": matrix["classification_policy"]["scope"],
        "reviewed_source_matrix_sha256": REVIEWED_SOURCE_MATRIX_SHA256,
        "counts": counts,
        "unknown_ids": [item["id"] for item in ordered_requirements if item["status"] == "UNKNOWN"],
        "red_ids": [item["id"] for item in ordered_requirements if item["status"] == "RED"],
        "pass_ids": [item["id"] for item in ordered_requirements if item["status"] == "PASS"],
        "wedge_component_ids": sorted(item["id"] for item in matrix["subcontract_wedge"]["components"]),
        "strongest_state": STRONGEST_STATE,
        "authority": dict(sorted(matrix["authority"].items())),
        "matrix_sha256": sha256_hex(normalized_matrix(matrix)),
    }
    if not _SHA256_RE.fullmatch(receipt["matrix_sha256"]):
        raise MatrixError("internal digest failure")
    return receipt


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise MatrixError("refusing to replace a symlink output")
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise MatrixError("refusing to write through a symlink directory")
    payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path, help="strict public-evidence matrix JSON")
    parser.add_argument("--output", type=Path, help="optional atomic receipt output")
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(load_matrix(args.matrix))
        if args.output:
            write_receipt(args.output, receipt)
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    except MatrixError as exc:
        parser.exit(2, f"matrix error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
