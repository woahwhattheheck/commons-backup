from __future__ import annotations

from typing import Any

from .constants import (
    CATEGORIES, EVIDENCE_KEYS, PUBLICABILITY, REUSE_SCOPES, SOURCE_CLASSES, STAGES,
    VERIFICATION_STATES, VERIFIER_CLASSES,
)
from .strict import (
    RegistryError, _parse_utc, _require_enum, _require_exact_keys, _require_id,
    _require_id_list, _require_sha, _require_str, _validate_metadata,
)

def _normalize_evidence(item: Any, index: int) -> dict[str, Any]:
    where = f"evidence[{index}]"
    item = _require_exact_keys(item, EVIDENCE_KEYS, where)
    category = _require_enum(item["category"], CATEGORIES, f"{where}.category")
    source_class = _require_enum(item["source_class"], SOURCE_CLASSES, f"{where}.source_class")
    verification_state = _require_enum(item["verification_state"], VERIFICATION_STATES, f"{where}.verification_state")
    verifier_class = _require_enum(item["verifier_class"], VERIFIER_CLASSES, f"{where}.verifier_class")
    if source_class == "SELF_ASSERTED" and verification_state == "VERIFIED":
        raise RegistryError(f"{where}:SELF_ASSERTED_CANNOT_BE_VERIFIED")
    if verification_state == "VERIFIED" and verifier_class == "NONE":
        raise RegistryError(f"{where}:VERIFIED_REQUIRES_VERIFIER")
    if verification_state != "VERIFIED" and verifier_class == "ISSUER" and source_class == "SELF_ASSERTED":
        raise RegistryError(f"{where}:SELF_ASSERTED_ISSUER_CONTRADICTION")

    reuse_scope = _require_enum(item["reuse_scope"], REUSE_SCOPES, f"{where}.reuse_scope")
    opportunity_ids = _require_id_list(item["opportunity_ids"], f"{where}.opportunity_ids")
    if reuse_scope == "GLOBAL" and opportunity_ids:
        raise RegistryError(f"{where}:GLOBAL_CANNOT_LIST_OPPORTUNITIES")
    if reuse_scope == "OPPORTUNITY_ONLY" and not opportunity_ids:
        raise RegistryError(f"{where}:OPPORTUNITY_ONLY_REQUIRES_SCOPE")

    stages = _require_id_list(item["stages"], f"{where}.stages", allowed=STAGES)
    if not stages:
        raise RegistryError(f"{where}:STAGES_EMPTY")

    issued = _parse_utc(item["issued_at"], f"{where}.issued_at")
    captured = _parse_utc(item["captured_at"], f"{where}.captured_at")
    expires = _parse_utc(item["expires_at"], f"{where}.expires_at", nullable=True)
    revoked = _parse_utc(item["revoked_at"], f"{where}.revoked_at", nullable=True)
    assert issued is not None and captured is not None
    if captured < issued:
        raise RegistryError(f"{where}:CAPTURE_BEFORE_ISSUE")
    if expires is not None and expires <= issued:
        raise RegistryError(f"{where}:EXPIRY_NOT_AFTER_ISSUE")
    if revoked is not None and revoked < issued:
        raise RegistryError(f"{where}:REVOCATION_BEFORE_ISSUE")

    subject_id = _require_id(item["subject_id"], f"{where}.subject_id", nullable=True)
    if category.startswith("REFERENCE_") and subject_id is None:
        raise RegistryError(f"{where}:REFERENCE_REQUIRES_SUBJECT")
    if category in {"STAFF_CV", "STAFF_AVAILABILITY"} and subject_id is None:
        raise RegistryError(f"{where}:STAFF_REQUIRES_SUBJECT")

    return {
        "id": _require_id(item["id"], f"{where}.id"),
        "category": category,
        "entity_id": _require_id(item["entity_id"], f"{where}.entity_id"),
        "subject_id": subject_id,
        "source_class": source_class,
        "issuer": _require_str(item["issuer"], f"{where}.issuer"),
        "descriptor": _require_str(item["descriptor"], f"{where}.descriptor"),
        "content_sha256": _require_sha(item["content_sha256"], f"{where}.content_sha256"),
        "captured_at": item["captured_at"],
        "issued_at": item["issued_at"],
        "expires_at": item["expires_at"],
        "verification_state": verification_state,
        "verifier_class": verifier_class,
        "reuse_scope": reuse_scope,
        "opportunity_ids": opportunity_ids,
        "stages": stages,
        "publicability": _require_enum(item["publicability"], PUBLICABILITY, f"{where}.publicability"),
        "supersedes": _require_id(item["supersedes"], f"{where}.supersedes", nullable=True),
        "revoked_at": item["revoked_at"],
        "metadata": _validate_metadata(category, item["metadata"], f"{where}.metadata"),
    }
