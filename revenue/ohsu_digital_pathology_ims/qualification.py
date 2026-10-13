# SPDX-License-Identifier: Apache-2.0
"""Deterministic, evidence-only qualification gate for OHSU RFP-2027-2012.

The public OHSU bid listing establishes opportunity identity and broad capability
needs, but explicitly says minimum bidder requirements live in the full RFP
package. This module therefore never infers bid eligibility from public summary
text. A READY decision requires an explicit, source-bound minimum-qualification
snapshot plus evidence for every declared minimum and a content-addressed
completeness manifest bound to the exact full-RFP capture.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Iterable

OPPORTUNITY_ID = "RFP-2027-2012"
PUBLIC_SOURCE = "https://www.ohsu.edu/procurement/bids"
ISSUE_DATE = "2026-09-11"
DUE_DATE = "2026-10-11"
AUTHORITY = "EVIDENCE_ONLY_NO_BID_SUBMISSION"
REQUIREMENTS_MANIFEST_SCHEMA = "ohsu-rfp-minimums-manifest/v1"

PUBLIC_CAPABILITIES = (
    "epic_beaker_bidirectional_integration",
    "end_to_end_digital_pathology_workflow",
    "native_and_third_party_ai_ia_integration",
    "centralized_image_management_viewing_sharing_analysis",
    "clinical_education_research_missions",
)


class QualificationError(ValueError):
    """Input is malformed or violates deterministic evidence rules."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise QualificationError("timestamps must be UTC strings ending in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise QualificationError("invalid UTC timestamp") from exc
    if dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise QualificationError("timestamp must resolve to UTC")
    return dt


def _nonempty_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{field} must be a non-empty string")
    return value.strip()


def _strict_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise QualificationError(f"{field} must be boolean")
    return value


def _finite_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise QualificationError(f"{field} must be numeric")
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise QualificationError(f"{field} must be numeric") from exc
    if not out.is_finite():
        raise QualificationError(f"{field} must be finite")
    return out


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _unique_rows(rows: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise QualificationError("evidence rows must be objects")
        ident = _nonempty_str(row.get(key), key)
        if ident in out:
            raise QualificationError(f"duplicate {key}: {ident}")
        out[ident] = row
    return out


def _minimum_projection(min_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    projection: list[dict[str, Any]] = []
    for requirement_id, row in min_rows.items():
        mandatory = _strict_bool(row.get("mandatory"), f"minimum {requirement_id} mandatory")
        text = _nonempty_str(row.get("text"), f"minimum {requirement_id} text")
        projection.append({"id": requirement_id, "mandatory": mandatory, "text": text})
    return sorted(projection, key=lambda row: row["id"])


def _requirements_manifest_holds(
    payload: dict[str, Any],
    full_rfp: dict[str, Any],
    minimum_projection: list[dict[str, Any]],
) -> tuple[list[str], str | None]:
    """Verify a source-bound completeness artifact for the minimum universe.

    The manifest is deliberately separate from `minimum_qualifications`: it
    commits to the exact RFP digest, row/mandatory counts, canonical requirement
    digest, and source coordinates. A content-addressed independent completeness
    attestation must commit to the same manifest core. Changing the requirement
    universe therefore requires changing the completeness artifact too.
    """
    holds: list[str] = []
    if not full_rfp.get("captured"):
        return holds, None

    manifest = payload.get("requirements_manifest")
    if not isinstance(manifest, dict):
        return ["REQUIREMENTS_MANIFEST_NOT_CAPTURED"], None

    manifest_sha256 = digest(manifest)
    declared_manifest_sha256 = full_rfp.get("requirements_manifest_sha256")
    if not _is_sha256(declared_manifest_sha256):
        holds.append("REQUIREMENTS_MANIFEST_DIGEST_INVALID")
    elif declared_manifest_sha256 != manifest_sha256:
        holds.append("REQUIREMENTS_MANIFEST_DIGEST_MISMATCH")

    if manifest.get("schema") != REQUIREMENTS_MANIFEST_SCHEMA:
        holds.append("REQUIREMENTS_MANIFEST_SCHEMA_INVALID")

    full_rfp_sha256 = full_rfp.get("sha256")
    if manifest.get("full_rfp_sha256") != full_rfp_sha256:
        holds.append("REQUIREMENTS_MANIFEST_RFP_MISMATCH")

    actual_count = len(minimum_projection)
    actual_mandatory_count = sum(1 for row in minimum_projection if row["mandatory"])
    if actual_mandatory_count < 1:
        holds.append("MANDATORY_QUALIFICATIONS_EMPTY")

    requirement_count = manifest.get("requirement_count")
    mandatory_count = manifest.get("mandatory_count")
    if isinstance(requirement_count, bool) or not isinstance(requirement_count, int) or requirement_count < 1:
        holds.append("REQUIREMENTS_MANIFEST_COUNT_INVALID")
    elif requirement_count != actual_count:
        holds.append("REQUIREMENTS_MANIFEST_COUNT_MISMATCH")
    if isinstance(mandatory_count, bool) or not isinstance(mandatory_count, int) or mandatory_count < 1:
        holds.append("REQUIREMENTS_MANIFEST_MANDATORY_COUNT_INVALID")
    elif mandatory_count != actual_mandatory_count:
        holds.append("REQUIREMENTS_MANIFEST_MANDATORY_COUNT_MISMATCH")

    expected_requirements_digest = digest(minimum_projection)
    requirements_digest = manifest.get("requirements_digest")
    if not _is_sha256(requirements_digest):
        holds.append("REQUIREMENTS_MANIFEST_REQUIREMENTS_DIGEST_INVALID")
    elif requirements_digest != expected_requirements_digest:
        holds.append("REQUIREMENTS_MANIFEST_REQUIREMENTS_DIGEST_MISMATCH")

    coordinates = manifest.get("source_coordinates")
    coordinate_map: dict[str, str] = {}
    if not isinstance(coordinates, list) or not coordinates:
        holds.append("REQUIREMENTS_MANIFEST_SOURCE_COORDINATES_INVALID")
    else:
        for coordinate in coordinates:
            if not isinstance(coordinate, dict):
                holds.append("REQUIREMENTS_MANIFEST_SOURCE_COORDINATES_INVALID")
                coordinate_map = {}
                break
            requirement_id = coordinate.get("requirement_id")
            locator = coordinate.get("locator")
            if (
                not isinstance(requirement_id, str)
                or not requirement_id.strip()
                or requirement_id in coordinate_map
                or not isinstance(locator, str)
                or not locator.strip()
            ):
                holds.append("REQUIREMENTS_MANIFEST_SOURCE_COORDINATES_INVALID")
                coordinate_map = {}
                break
            coordinate_map[requirement_id.strip()] = locator.strip()
        if coordinate_map and set(coordinate_map) != {row["id"] for row in minimum_projection}:
            holds.append("REQUIREMENTS_MANIFEST_SOURCE_COORDINATES_MISMATCH")

    manifest_core = {
        "schema": manifest.get("schema"),
        "full_rfp_sha256": manifest.get("full_rfp_sha256"),
        "requirement_count": manifest.get("requirement_count"),
        "mandatory_count": manifest.get("mandatory_count"),
        "requirements_digest": manifest.get("requirements_digest"),
        "source_coordinates": manifest.get("source_coordinates"),
    }
    manifest_core_sha256 = digest(manifest_core)
    attestation = manifest.get("completeness_attestation")
    if not isinstance(attestation, dict):
        holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_MISSING")
    else:
        if attestation.get("kind") != "independent_completeness_review":
            holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_INVALID")
        try:
            complete = _strict_bool(
                attestation.get("complete"),
                "requirements_manifest.completeness_attestation.complete",
            )
        except QualificationError:
            complete = False
            holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_INVALID")
        if not complete:
            holds.append("REQUIREMENTS_COMPLETENESS_NOT_ATTESTED")

        for field in ("reviewer", "reference"):
            value = attestation.get(field)
            if not isinstance(value, str) or not value.strip():
                holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_INVALID")
                break
        attestation_core = {
            "kind": attestation.get("kind"),
            "complete": attestation.get("complete"),
            "reviewer": attestation.get("reviewer"),
            "reference": attestation.get("reference"),
            "manifest_core_sha256": attestation.get("manifest_core_sha256"),
        }
        attestation_sha256 = attestation.get("sha256")
        if not _is_sha256(attestation_sha256):
            holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_INVALID")
        elif attestation_sha256 != digest(attestation_core):
            holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_DIGEST_MISMATCH")
        if full_rfp.get("completeness_attestation_sha256") != attestation_sha256:
            holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_RFP_BINDING_MISMATCH")
        if attestation.get("manifest_core_sha256") != manifest_core_sha256:
            holds.append("REQUIREMENTS_COMPLETENESS_ATTESTATION_MANIFEST_MISMATCH")

    return sorted(set(holds)), manifest_sha256


def evaluate(payload: dict[str, Any], *, evaluated_at: str) -> dict[str, Any]:
    """Evaluate a captured qualification bundle.

    `evaluated_at` is trusted verifier time supplied outside the evidence. The
    receipt binds source, minimum requirements, completeness manifest,
    capability claims and evidence; it never authorizes outreach, intent-to-bid
    or proposal submission.
    """
    if not isinstance(payload, dict):
        raise QualificationError("payload must be an object")
    now = _parse_utc(evaluated_at)

    opportunity = payload.get("opportunity")
    if not isinstance(opportunity, dict):
        raise QualificationError("opportunity must be an object")
    if opportunity.get("id") != OPPORTUNITY_ID:
        raise QualificationError("wrong opportunity id")
    if opportunity.get("public_source") != PUBLIC_SOURCE:
        raise QualificationError("wrong public source")
    if opportunity.get("issue_date") != ISSUE_DATE or opportunity.get("due_date") != DUE_DATE:
        raise QualificationError("opportunity date mismatch")

    captured_at = _parse_utc(_nonempty_str(payload.get("captured_at"), "captured_at"))
    if captured_at > now:
        raise QualificationError("capture time is in the future")
    due = datetime.fromisoformat(DUE_DATE + "T23:59:59+00:00")

    full_rfp = payload.get("full_rfp")
    holds: list[str] = []
    if not isinstance(full_rfp, dict):
        holds.append("FULL_RFP_PACKAGE_NOT_CAPTURED")
        full_rfp = {}
    else:
        if not _strict_bool(full_rfp.get("captured", False), "full_rfp.captured"):
            holds.append("FULL_RFP_PACKAGE_NOT_CAPTURED")
        source = full_rfp.get("source")
        sha256 = full_rfp.get("sha256")
        if full_rfp.get("captured"):
            if not isinstance(source, str) or not source.strip():
                holds.append("FULL_RFP_SOURCE_MISSING")
            if not _is_sha256(sha256):
                holds.append("FULL_RFP_DIGEST_INVALID")

    minimums = payload.get("minimum_qualifications")
    if not isinstance(minimums, list) or not minimums:
        holds.append("MINIMUM_QUALIFICATIONS_NOT_CAPTURED")
        minimums = []
    min_rows = _unique_rows(minimums, "id") if minimums else {}
    minimum_projection = _minimum_projection(min_rows) if min_rows else []

    manifest_holds, manifest_sha256 = _requirements_manifest_holds(
        payload, full_rfp, minimum_projection
    )
    holds.extend(manifest_holds)

    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise QualificationError("evidence must be a list")
    evidence_rows = _unique_rows(evidence, "requirement_id")

    missing_minimum_evidence: list[str] = []
    failed_minimums: list[str] = []
    for requirement_id, row in min_rows.items():
        if type(row.get("mandatory")) is not bool:
            raise QualificationError(f"minimum {requirement_id} mandatory must be boolean")
        if not row["mandatory"]:
            continue
        proof = evidence_rows.get(requirement_id)
        if proof is None:
            missing_minimum_evidence.append(requirement_id)
            continue
        result = proof.get("result")
        if result not in {"PASS", "FAIL"}:
            raise QualificationError(f"evidence result for {requirement_id} must be PASS or FAIL")
        _nonempty_str(proof.get("reference"), f"evidence reference for {requirement_id}")
        _nonempty_str(proof.get("sha256"), f"evidence sha256 for {requirement_id}")
        if not _is_sha256(proof["sha256"]):
            raise QualificationError(f"evidence sha256 for {requirement_id} must be lowercase hex")
        if result == "FAIL":
            failed_minimums.append(requirement_id)

    if missing_minimum_evidence:
        holds.append("MANDATORY_EVIDENCE_MISSING")
    if failed_minimums:
        holds.append("MANDATORY_QUALIFICATION_FAILED")
    if now > due:
        holds.append("OPPORTUNITY_DEADLINE_PASSED")

    capabilities = payload.get("public_capability_claims", [])
    if not isinstance(capabilities, list):
        raise QualificationError("public_capability_claims must be a list")
    capability_set = set()
    for capability in capabilities:
        capability_set.add(_nonempty_str(capability, "capability"))
    unknown = sorted(capability_set - set(PUBLIC_CAPABILITIES))
    if unknown:
        raise QualificationError("unknown public capability claim: " + ",".join(unknown))
    missing_public = sorted(set(PUBLIC_CAPABILITIES) - capability_set)
    if missing_public:
        holds.append("PUBLIC_CAPABILITY_MATRIX_INCOMPLETE")

    decision = "READY_FOR_INTERNAL_BID_REVIEW" if not holds else "HOLD"
    evidence_digest = digest({
        "opportunity": opportunity,
        "captured_at": payload.get("captured_at"),
        "full_rfp": full_rfp,
        "requirements_manifest": payload.get("requirements_manifest"),
        "minimum_qualifications": minimums,
        "public_capability_claims": sorted(capability_set),
        "evidence": evidence,
    })
    receipt = {
        "schema": "ohsu-digital-pathology-qualification/v2",
        "opportunity_id": OPPORTUNITY_ID,
        "decision": decision,
        "holds": sorted(set(holds)),
        "missing_mandatory_evidence": sorted(missing_minimum_evidence),
        "failed_mandatory_qualifications": sorted(failed_minimums),
        "missing_public_capabilities": missing_public,
        "evaluated_at": evaluated_at,
        "requirements_manifest_sha256": manifest_sha256,
        "evidence_digest": evidence_digest,
        "authority": AUTHORITY,
        "outreach_authorized": False,
        "intent_to_bid_authorized": False,
        "proposal_submission_authorized": False,
        "clinical_use_authorized": False,
    }
    receipt["receipt_digest"] = digest(receipt)
    return receipt


def verify(payload: dict[str, Any], receipt: dict[str, Any], *, evaluated_at: str) -> bool:
    expected = evaluate(payload, evaluated_at=evaluated_at)
    return expected == receipt
