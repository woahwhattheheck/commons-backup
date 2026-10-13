"""Evidence-readiness compiler for NUMIH AI SAD 2025-0154-00-00-MPF.

The packet is caller-authored.  Positive readiness can therefore come only from a
separate evidence bundle whose exact retained bytes are decoded, length-checked,
and SHA-256 verified by this module.  The bundle proves artifact retention, not
legal validity, issuer truth, sponsor scoring, admission, award, or revenue.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any

SCHEMA = "numih-ai-sad-admission-readiness/v1"
BUNDLE_SCHEMA = "numih-ai-sad-evidence-bundle/v1"
RESULT_SCHEMA = "numih-ai-sad-admission-readiness-result/v2"
RECEIPT_SCHEMA = "numih-ai-sad-admission-readiness-receipt/v2"
MAX_TEXT = 4096
MAX_EVIDENCE_ROWS = 512
MAX_ARTIFACT_BYTES = 2_000_000
MAX_BUNDLE_BYTES = 16_000_000

CATS = {
    1: "AI tools for administrative functions",
    2: "AI tools for development and hosting",
    3: "Cross-cutting AI tools",
    4: "AI technology foundation",
}
DIMS = (
    (
        "legal_aptitude_compliance",
        20,
        (
            "legal_registration",
            "binding_authority",
            "exclusion_labor_compliance",
            "gdpr_data_location",
            "professional_liability_insurance",
        ),
    ),
    ("recent_ai_references", 30, ("recent_ai_reference",)),
    (
        "security_ethics_ai_compliance",
        30,
        (
            "security_questionnaire",
            "ssi_charter",
            "confidentiality_commitment",
            "ai_ethics_compliance",
        ),
    ),
    (
        "economic_financial_capacity",
        20,
        ("global_turnover", "ai_domain_turnover_or_substitute"),
    ),
)
APPLICANT_ONLY = {
    "legal_registration",
    "binding_authority",
    "exclusion_labor_compliance",
}
STATUSES = {"EVIDENCED", "CLAIMED_UNVERIFIED", "MISSING"}
TRANSLATIONS = {
    "ORIGINAL_FR",
    "CERTIFIED_TRANSLATION",
    "WORKING_TRANSLATION",
    "UNTRANSLATED",
}
BOUND_COVERAGE = "RETAINED_SOURCE_BYTES"


class ValidationError(ValueError):
    """Input or bundle violates the closed schema/authority contract."""


def _constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON constant forbidden: {value}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads_strict(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _obj(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object")
    return value


def _arr(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{path} must be an array")
    return value


def _str(value: Any, path: str, *, empty: bool = False) -> str:
    if type(value) is not str:
        raise ValidationError(f"{path} must be a string")
    if not empty and not value.strip():
        raise ValidationError(f"{path} must not be empty")
    if len(value) > MAX_TEXT:
        raise ValidationError(f"{path} too long")
    return value


def _int(value: Any, path: str, *, minimum: int = 0, maximum: int) -> int:
    if type(value) is not int:
        raise ValidationError(f"{path} must be an integer")
    if value < minimum or value > maximum:
        raise ValidationError(f"{path} outside allowed range")
    return value


def _only(obj: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise ValidationError(f"{path} has unknown fields: {sorted(unknown)}")


def _sha(value: Any, path: str) -> str:
    text = _str(value, path).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValidationError(f"{path} must be SHA-256 hex")
    return text


def _party(raw: Any, path: str, role: str) -> dict[str, Any]:
    obj = _obj(raw, path)
    allowed = {"id", "display_name"}
    if role == "PARTNER":
        allowed.add("commitment_evidence_id")
    _only(obj, allowed, path)
    commitment = obj.get("commitment_evidence_id")
    if commitment is not None:
        commitment = _str(commitment, path + ".commitment_evidence_id")
    return {
        "id": _str(obj.get("id"), path + ".id"),
        "display_name": _str(obj.get("display_name"), path + ".display_name"),
        "role": role,
        "commitment_evidence_id": commitment,
    }


def _evidence(raw: Any, path: str) -> dict[str, Any]:
    obj = _obj(raw, path)
    _only(
        obj,
        {
            "id",
            "party_id",
            "kind",
            "status",
            "source",
            "language",
            "translation_status",
            "note",
        },
        path,
    )
    status = _str(obj.get("status"), path + ".status")
    translation = _str(
        obj.get("translation_status", "UNTRANSLATED"),
        path + ".translation_status",
    )
    if status not in STATUSES:
        raise ValidationError(f"{path}.status unsupported")
    if translation not in TRANSLATIONS:
        raise ValidationError(f"{path}.translation_status unsupported")
    language = _str(obj.get("language", "und"), path + ".language")
    if translation == "ORIGINAL_FR" and language.lower() != "fr":
        raise ValidationError(
            f"{path}.translation_status ORIGINAL_FR requires language=fr"
        )

    source = obj.get("source")
    parsed_source: dict[str, str] | None = None
    if status == "EVIDENCED":
        source_obj = _obj(source, path + ".source")
        _only(source_obj, {"locator", "sha256", "generation"}, path + ".source")
        parsed_source = {
            "locator": _str(source_obj.get("locator"), path + ".source.locator"),
            "sha256": _sha(source_obj.get("sha256"), path + ".source.sha256"),
            "generation": _str(
                source_obj.get("generation"), path + ".source.generation"
            ),
        }
    elif source is not None:
        raise ValidationError(f"{path}.source allowed only when status=EVIDENCED")

    return {
        "id": _str(obj.get("id"), path + ".id"),
        "party_id": _str(obj.get("party_id"), path + ".party_id"),
        "kind": _str(obj.get("kind"), path + ".kind"),
        "status": status,
        "source": parsed_source,
        "language": language,
        "translation_status": translation,
        "note": _str(obj.get("note", ""), path + ".note", empty=True),
    }


def validate_packet(
    packet: Any,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[int],
    list[dict[str, Any]],
    dict[str, str],
]:
    obj = _obj(packet, "$")
    _only(obj, {"schema", "applicant", "partners", "categories", "evidence", "dce"}, "$")
    if obj.get("schema") != SCHEMA:
        raise ValidationError(f"$.schema must be {SCHEMA}")

    applicant = _party(obj.get("applicant"), "$.applicant", "APPLICANT")
    partners = [
        _party(value, f"$.partners[{index}]", "PARTNER")
        for index, value in enumerate(_arr(obj.get("partners", []), "$.partners"))
    ]
    if len(partners) > 15:
        raise ValidationError("too many partners")
    party_ids = [applicant["id"], *(partner["id"] for partner in partners)]
    if len(party_ids) != len(set(party_ids)):
        raise ValidationError("duplicate party id")

    categories: list[int] = []
    for index, value in enumerate(_arr(obj.get("categories"), "$.categories")):
        if type(value) is not int:
            raise ValidationError(f"$.categories[{index}] must be an integer")
        categories.append(value)
    if not categories or len(categories) > 4:
        raise ValidationError("$.categories must contain 1..4 entries")
    if len(categories) != len(set(categories)):
        raise ValidationError("duplicate category")
    if any(category not in CATS for category in categories):
        raise ValidationError("categories must be integers 1..4")

    evidence = [
        _evidence(value, f"$.evidence[{index}]")
        for index, value in enumerate(_arr(obj.get("evidence"), "$.evidence"))
    ]
    if len(evidence) > MAX_EVIDENCE_ROWS:
        raise ValidationError("too many evidence rows")
    evidence_ids = [row["id"] for row in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValidationError("duplicate evidence id")

    known_parties = set(party_ids)
    for row in evidence:
        if row["party_id"] not in known_parties:
            raise ValidationError(f"unknown evidence party: {row['party_id']}")
        if row["kind"] in APPLICANT_ONLY and row["party_id"] != applicant["id"]:
            raise ValidationError(f"{row['kind']} must belong to applicant")

    evidence_by_id = {row["id"]: row for row in evidence}
    for partner in partners:
        commitment_id = partner["commitment_evidence_id"]
        if commitment_id:
            row = evidence_by_id.get(commitment_id)
            if (
                not row
                or row["party_id"] != partner["id"]
                or row["kind"] != "partner_capacity_commitment"
            ):
                raise ValidationError(
                    f"partner {partner['id']} commitment evidence is cross-party or wrong kind"
                )

    dce_obj = _obj(obj.get("dce"), "$.dce")
    _only(dce_obj, {"document_id", "sha256", "generation", "source_locator"}, "$.dce")
    dce = {
        "document_id": _str(dce_obj.get("document_id"), "$.dce.document_id"),
        "sha256": _sha(dce_obj.get("sha256"), "$.dce.sha256"),
        "generation": _str(dce_obj.get("generation"), "$.dce.generation"),
        "source_locator": _str(
            dce_obj.get("source_locator"), "$.dce.source_locator"
        ),
    }
    return applicant, partners, sorted(categories), evidence, dce


def _decode_bundle_content(value: Any, path: str) -> bytes:
    text = _str(value, path)
    if len(text) > (MAX_ARTIFACT_BYTES * 4 // 3) + 16:
        raise ValidationError(f"{path} exceeds encoded size limit")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(f"{path} must be canonical base64") from exc


def validate_bundle(bundle: Any | None) -> dict[str, Any]:
    """Validate and seal exact source bytes supplied outside the packet.

    A missing bundle is a supported fail-closed state: packet metadata can still be
    inspected, but no row receives positive retained-byte authority.
    """
    if bundle is None:
        return {
            "present": False,
            "bundle_id": None,
            "generation": None,
            "root_sha256": None,
            "entries": {},
            "artifact_count": 0,
            "retained_bytes": 0,
        }

    obj = _obj(bundle, "$bundle")
    _only(obj, {"schema", "bundle_id", "generation", "artifacts"}, "$bundle")
    if obj.get("schema") != BUNDLE_SCHEMA:
        raise ValidationError(f"$bundle.schema must be {BUNDLE_SCHEMA}")
    bundle_id = _str(obj.get("bundle_id"), "$bundle.bundle_id")
    generation = _str(obj.get("generation"), "$bundle.generation")
    artifacts_raw = _arr(obj.get("artifacts"), "$bundle.artifacts")
    if len(artifacts_raw) > MAX_EVIDENCE_ROWS:
        raise ValidationError("too many bundle artifacts")

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_bytes = 0
    for index, raw in enumerate(artifacts_raw):
        path = f"$bundle.artifacts[{index}]"
        item = _obj(raw, path)
        _only(
            item,
            {
                "evidence_id",
                "party_id",
                "kind",
                "locator",
                "generation",
                "sha256",
                "byte_length",
                "media_type",
                "content_b64",
            },
            path,
        )
        evidence_id = _str(item.get("evidence_id"), path + ".evidence_id")
        if evidence_id in seen:
            raise ValidationError(f"duplicate bundle evidence id: {evidence_id}")
        seen.add(evidence_id)
        content = _decode_bundle_content(item.get("content_b64"), path + ".content_b64")
        declared_length = _int(
            item.get("byte_length"),
            path + ".byte_length",
            maximum=MAX_ARTIFACT_BYTES,
        )
        if len(content) != declared_length:
            raise ValidationError(f"{path}.byte_length does not match retained bytes")
        declared_sha = _sha(item.get("sha256"), path + ".sha256")
        observed_sha = hashlib.sha256(content).hexdigest()
        if observed_sha != declared_sha:
            raise ValidationError(f"{path}.sha256 does not match retained bytes")
        total_bytes += len(content)
        if total_bytes > MAX_BUNDLE_BYTES:
            raise ValidationError("bundle retained bytes exceed total limit")
        entries.append(
            {
                "evidence_id": evidence_id,
                "party_id": _str(item.get("party_id"), path + ".party_id"),
                "kind": _str(item.get("kind"), path + ".kind"),
                "locator": _str(item.get("locator"), path + ".locator"),
                "generation": _str(item.get("generation"), path + ".generation"),
                "sha256": observed_sha,
                "byte_length": len(content),
                "media_type": _str(item.get("media_type"), path + ".media_type"),
            }
        )

    entries.sort(key=lambda entry: entry["evidence_id"])
    root_payload = {
        "schema": BUNDLE_SCHEMA,
        "bundle_id": bundle_id,
        "generation": generation,
        "artifacts": entries,
    }
    return {
        "present": True,
        "bundle_id": bundle_id,
        "generation": generation,
        "root_sha256": digest_json(root_payload),
        "entries": {entry["evidence_id"]: entry for entry in entries},
        "artifact_count": len(entries),
        "retained_bytes": total_bytes,
    }


def _evidence_authority(
    evidence: list[dict[str, Any]], bundle: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    authority: dict[str, dict[str, Any]] = {}
    for row in evidence:
        if row["status"] != "EVIDENCED":
            authority[row["id"]] = {
                "bound": False,
                "state": "NOT_DECLARED_EVIDENCED",
                "bundle_sha256": None,
                "bundle_generation": None,
            }
            continue
        if not bundle["present"]:
            authority[row["id"]] = {
                "bound": False,
                "state": "SOURCE_BUNDLE_MISSING",
                "bundle_sha256": None,
                "bundle_generation": None,
            }
            continue
        entry = bundle["entries"].get(row["id"])
        if entry is None:
            authority[row["id"]] = {
                "bound": False,
                "state": "SOURCE_ENTRY_MISSING",
                "bundle_sha256": bundle["root_sha256"],
                "bundle_generation": bundle["generation"],
            }
            continue
        source = row["source"]
        assert source is not None
        expected = {
            "party_id": row["party_id"],
            "kind": row["kind"],
            "locator": source["locator"],
            "generation": source["generation"],
            "sha256": source["sha256"],
        }
        observed = {key: entry[key] for key in expected}
        mismatches = sorted(key for key in expected if expected[key] != observed[key])
        if mismatches:
            authority[row["id"]] = {
                "bound": False,
                "state": "SOURCE_BINDING_MISMATCH",
                "mismatched_fields": mismatches,
                "bundle_sha256": bundle["root_sha256"],
                "bundle_generation": bundle["generation"],
            }
            continue
        authority[row["id"]] = {
            "bound": True,
            "state": BOUND_COVERAGE,
            "mismatched_fields": [],
            "bundle_sha256": bundle["root_sha256"],
            "bundle_generation": bundle["generation"],
            "byte_length": entry["byte_length"],
            "media_type": entry["media_type"],
        }
    return authority


def _committed(
    partner: dict[str, Any],
    evidence_by_id: dict[str, dict[str, Any]],
    authority: dict[str, dict[str, Any]],
) -> bool:
    commitment_id = partner["commitment_evidence_id"]
    row = evidence_by_id.get(commitment_id) if commitment_id else None
    return bool(
        row
        and row["status"] == "EVIDENCED"
        and authority[row["id"]]["bound"]
    )


def _effective(
    kind: str,
    applicant_id: str,
    partner_by_id: dict[str, dict[str, Any]],
    evidence: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    authority: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in evidence:
        if (
            row["kind"] != kind
            or row["status"] != "EVIDENCED"
            or not authority[row["id"]]["bound"]
        ):
            continue
        if row["party_id"] == applicant_id:
            result.append(row)
        elif kind not in APPLICANT_ONLY:
            partner = partner_by_id.get(row["party_id"])
            if partner and _committed(partner, evidence_by_id, authority):
                result.append(row)
    return sorted(result, key=lambda row: (row["party_id"], row["id"]))


def _coverage(
    kind: str,
    applicant_id: str,
    partner_by_id: dict[str, dict[str, Any]],
    evidence: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    authority: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    effective = _effective(
        kind,
        applicant_id,
        partner_by_id,
        evidence,
        evidence_by_id,
        authority,
    )
    if effective:
        row = effective[0]
        binding = authority[row["id"]]
        return {
            "requirement": kind,
            "coverage": BOUND_COVERAGE,
            "party_id": row["party_id"],
            "evidence_id": row["id"],
            "source_generation": row["source"]["generation"],
            "source_sha256": row["source"]["sha256"],
            "retained_byte_length": binding["byte_length"],
        }

    rows = sorted(
        (row for row in evidence if row["kind"] == kind),
        key=lambda row: (row["party_id"], row["id"]),
    )
    for row in rows:
        if row["status"] == "CLAIMED_UNVERIFIED":
            return {
                "requirement": kind,
                "coverage": "CLAIMED_UNVERIFIED",
                "party_id": row["party_id"],
                "evidence_id": row["id"],
                "source_generation": None,
                "source_sha256": None,
                "retained_byte_length": None,
            }
    for row in rows:
        if row["status"] == "EVIDENCED" and not authority[row["id"]]["bound"]:
            return {
                "requirement": kind,
                "coverage": authority[row["id"]]["state"],
                "party_id": row["party_id"],
                "evidence_id": row["id"],
                "source_generation": None,
                "source_sha256": None,
                "retained_byte_length": None,
            }
    for row in rows:
        partner = partner_by_id.get(row["party_id"])
        if (
            row["status"] == "EVIDENCED"
            and authority[row["id"]]["bound"]
            and partner
            and not _committed(partner, evidence_by_id, authority)
        ):
            return {
                "requirement": kind,
                "coverage": "PARTNER_COMMITMENT_MISSING",
                "party_id": row["party_id"],
                "evidence_id": row["id"],
                "source_generation": row["source"]["generation"],
                "source_sha256": row["source"]["sha256"],
                "retained_byte_length": authority[row["id"]]["byte_length"],
            }
    return {
        "requirement": kind,
        "coverage": "MISSING",
        "party_id": None,
        "evidence_id": None,
        "source_generation": None,
        "source_sha256": None,
        "retained_byte_length": None,
    }


def _needs_translation(row: dict[str, Any]) -> bool:
    status = row["translation_status"]
    language = row["language"].lower()
    if status in {"WORKING_TRANSLATION", "UNTRANSLATED"}:
        return True
    if language != "fr" and status != "CERTIFIED_TRANSLATION":
        return True
    return False


def compile_packet(packet: Any, evidence_bundle: Any | None = None) -> dict[str, Any]:
    applicant, partners, categories, evidence, dce = validate_packet(packet)
    bundle = validate_bundle(evidence_bundle)
    partner_by_id = {partner["id"]: partner for partner in partners}
    evidence_by_id = {row["id"]: row for row in evidence}
    authority = _evidence_authority(evidence, bundle)

    dimensions: list[dict[str, Any]] = []
    total = 0.0
    core_complete = True
    for name, weight, requirements in DIMS:
        rows = [
            _coverage(
                kind,
                applicant["id"],
                partner_by_id,
                evidence,
                evidence_by_id,
                authority,
            )
            for kind in requirements
        ]
        retained = sum(row["coverage"] == BOUND_COVERAGE for row in rows)
        points = weight * retained / len(rows)
        total += points
        core_complete = core_complete and retained == len(rows)
        dimensions.append(
            {
                "dimension": name,
                "published_weight": weight,
                "requirements_total": len(rows),
                "requirements_with_retained_source_bytes": retained,
                "retained_evidence_coverage_points": round(points, 6),
                "rows": rows,
            }
        )

    category_rows: list[dict[str, Any]] = []
    categories_complete = True
    for category in categories:
        rows = _effective(
            f"category_fit_{category}",
            applicant["id"],
            partner_by_id,
            evidence,
            evidence_by_id,
            authority,
        )
        if rows:
            row = rows[0]
            category_rows.append(
                {
                    "category": category,
                    "name": CATS[category],
                    "state": BOUND_COVERAGE,
                    "party_id": row["party_id"],
                    "evidence_id": row["id"],
                }
            )
        else:
            categories_complete = False
            category_rows.append(
                {
                    "category": category,
                    "name": CATS[category],
                    "state": "HOLD",
                    "party_id": None,
                    "evidence_id": None,
                }
            )

    translation_queue = sorted(
        (
            {
                "evidence_id": row["id"],
                "party_id": row["party_id"],
                "language": row["language"],
                "translation_status": row["translation_status"],
                "action": "OWNER_REVIEW_FRENCH_TRANSLATION_AND_CERTIFICATION_REQUIREMENT",
            }
            for row in evidence
            if row["status"] == "EVIDENCED"
            and authority[row["id"]]["bound"]
            and _needs_translation(row)
        ),
        key=lambda item: (item["party_id"], item["evidence_id"]),
    )
    authority_queue = sorted(
        (
            {
                "evidence_id": row["id"],
                "party_id": row["party_id"],
                "kind": row["kind"],
                "state": authority[row["id"]]["state"],
                "mismatched_fields": authority[row["id"]].get(
                    "mismatched_fields", []
                ),
                "action": "RETAIN_AND_BIND_EXACT_SOURCE_BYTES_IN_EVIDENCE_BUNDLE",
            }
            for row in evidence
            if row["status"] == "EVIDENCED" and not authority[row["id"]]["bound"]
        ),
        key=lambda item: (item["party_id"], item["evidence_id"]),
    )

    packet_ready = (
        evidence_bundle is not None
        and core_complete
        and categories_complete
        and not translation_queue
        and not authority_queue
    )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "operation": "2025-0154-00-00-MPF",
        "applicant": {
            "party_id": applicant["id"],
            "display_name": applicant["display_name"],
        },
        "partners": [
            {
                "party_id": partner["id"],
                "display_name": partner["display_name"],
                "commitment_evidence_id": partner["commitment_evidence_id"],
                "capacity_composable": _committed(
                    partner, evidence_by_id, authority
                ),
            }
            for partner in sorted(partners, key=lambda partner: partner["id"])
        ],
        "categories": category_rows,
        "rubric": {
            "label": "PUBLISHED_RUBRIC_RETAINED_EVIDENCE_COVERAGE_NOT_SPONSOR_SCORE",
            "published_total_weight": 100,
            "retained_evidence_coverage_points": round(total, 6),
            "dimensions": dimensions,
        },
        "evidence_bundle": {
            "present": bundle["present"],
            "bundle_id": bundle["bundle_id"],
            "generation": bundle["generation"],
            "root_sha256": bundle["root_sha256"],
            "artifact_count": bundle["artifact_count"],
            "retained_bytes": bundle["retained_bytes"],
            "authority_label": "EXACT_RETAINED_BYTES_MATCH_MANIFEST_NOT_EXTERNAL_SEMANTIC_TRUTH",
        },
        "evidence_authority_queue": authority_queue,
        "translation_queue": translation_queue,
        "dce": {
            **dce,
            "currentness": "CURRENTNESS_UNVERIFIED",
            "reason": "Retained packet bytes cannot establish latest authoritative PLACE document currentness.",
        },
        "packet_state": (
            "PACKET_REVIEW_READY"
            if evidence_bundle is not None and packet_ready
            else "INCOMPLETE_EVIDENCE"
        ),
        "external_submission_state": "HOLD_CURRENTNESS_AND_OWNER_ACTIONS",
        "owner_actions": [
            "Name and verify the actual applicant legal entity and national registration mapping.",
            "Refresh the authoritative PLACE DCE immediately before admission work.",
            "Confirm current foreign-bidder filing, certificate, and French translation requirements.",
            "Resolve every evidence-bundle and translation/certification queue item.",
            "Independently verify the legal/semantic truth of retained source documents and partner commitments.",
            "Complete and verify current DUME, security questionnaire, SSI/confidentiality materials.",
            "Review pricing, declarations, e-signature and deposit in the provider surface; this compiler performs none.",
        ],
        "authority": {
            "buyer_contact": False,
            "provider_login_or_account": False,
            "dume_certification": False,
            "legal_declaration": False,
            "electronic_signature": False,
            "pricing_commitment": False,
            "submission_or_deposit": False,
            "admission": False,
            "contract_award": False,
            "payment": False,
            "recognized_revenue": False,
        },
        "disclaimer": (
            "Retained-byte packet-readiness compiler only. Coverage points mirror published "
            "rubric weights for artifact completeness; they are not a sponsor score, semantic "
            "verification, eligibility/admission prediction, legal opinion, award or revenue claim."
        ),
    }
    result["receipt"] = {
        "schema": RECEIPT_SCHEMA,
        "packet_sha256": digest_json(packet),
        "bundle_root_sha256": bundle["root_sha256"],
        "result_sha256": digest_json(result),
    }
    return result


def verify_result(
    packet: Any, result: Any, evidence_bundle: Any | None = None
) -> bool:
    if type(result) is not dict or type(result.get("receipt")) is not dict:
        return False
    receipt = result["receipt"]
    semantic = dict(result)
    semantic.pop("receipt", None)
    try:
        bundle = validate_bundle(evidence_bundle)
        rebuilt = compile_packet(packet, evidence_bundle)
    except (ValidationError, TypeError, ValueError):
        return False
    if evidence_bundle is None:
        return False
    return (
        receipt.get("schema") == RECEIPT_SCHEMA
        and receipt.get("packet_sha256") == digest_json(packet)
        and receipt.get("bundle_root_sha256") == bundle["root_sha256"]
        and receipt.get("result_sha256") == digest_json(semantic)
        and rebuilt == result
    )


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# NUMIH AI SAD admission-readiness packet",
        "",
        f"- Packet state: **{result['packet_state']}**",
        f"- External submission state: **{result['external_submission_state']}**",
        f"- DCE currentness: **{result['dce']['currentness']}**",
        (
            "- Published-rubric retained-evidence coverage: "
            f"**{result['rubric']['retained_evidence_coverage_points']}/100** "
            "(not a sponsor score)"
        ),
        (
            "- Evidence bundle root: `"
            f"{result['evidence_bundle']['root_sha256'] or 'MISSING'}`"
        ),
        "",
        "## Categories",
        "",
    ]
    for row in result["categories"]:
        suffix = (
            f" via `{row['party_id']}` / `{row['evidence_id']}`"
            if row["evidence_id"]
            else ""
        )
        lines.append(
            f"- {row['category']} — {row['name']}: **{row['state']}**{suffix}"
        )
    lines += ["", "## Evidence-authority queue", ""]
    if result["evidence_authority_queue"]:
        lines.extend(
            f"- `{row['evidence_id']}`: **{row['state']}** — {row['action']}"
            for row in result["evidence_authority_queue"]
        )
    else:
        lines.append("- Every counted artifact is bound to exact retained bundle bytes.")
    lines += ["", "## Translation/certification queue", ""]
    if result["translation_queue"]:
        lines.extend(
            (
                f"- `{row['evidence_id']}` ({row['language']}, "
                f"{row['translation_status']}): {row['action']}"
            )
            for row in result["translation_queue"]
        )
    else:
        lines.append("- No unresolved queue item in bound supplied evidence.")
    lines += ["", "## Owner actions", ""]
    lines.extend(f"- {action}" for action in result["owner_actions"])
    lines += [
        "",
        "## Authority ceiling",
        "",
        "All external mutation/award/payment/revenue authority fields are `false`.",
        "",
        result["disclaimer"],
        "",
    ]
    return "\n".join(lines)
