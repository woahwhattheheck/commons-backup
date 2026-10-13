from __future__ import annotations

from datetime import datetime
from typing import Any

from ._common import (
    AUDIT_DOCUMENT,
    GOOD_STANDING_DOCUMENT,
    SEMANTIC_AUTHORITY_MAX_AGE_SECONDS,
    QualificationInputError,
    _SEMANTIC_DOCUMENTS,
    _keys,
    _object,
)

def _semantic_document_states(
    *,
    documents: dict[str, dict[str, Any]],
    contract: dict[str, Any],
    evaluated: datetime,
    authority: dict[str, Any] | None,
) -> tuple[set[str], dict[str, str]]:
    holds: set[str] = set()
    states: dict[str, str] = {}
    policies = _object(
        contract.get("document_semantic_requirements"),
        "source contract document_semantic_requirements",
    )
    if set(policies) != set(_SEMANTIC_DOCUMENTS):
        raise QualificationInputError("compiled document semantic requirement set mismatch")
    if authority is None:
        for doc_id in sorted(_SEMANTIC_DOCUMENTS):
            if documents[doc_id]["status"] == "READY":
                holds.add(f"DOCUMENT_SEMANTICS_UNVERIFIED:{doc_id}")
                states[doc_id] = "AUTHORITY_UNAVAILABLE"
            else:
                states[doc_id] = "NOT_READY"
        return holds, states

    issued_at = authority["issued_at"]
    if issued_at > evaluated:
        raise QualificationInputError("semantic authority envelope is future-dated")
    if (evaluated - issued_at).total_seconds() > SEMANTIC_AUTHORITY_MAX_AGE_SECONDS:
        holds.add("SEMANTIC_AUTHORITY_GENERATION_STALE")
    index = {
        (row["document_id"], row["document_evidence_sha256"]): row
        for row in authority["rows"]
    }
    for doc_id in sorted(_SEMANTIC_DOCUMENTS):
        document = documents[doc_id]
        if document["status"] != "READY":
            states[doc_id] = "NOT_READY"
            continue
        row = index.get((doc_id, document["evidence_sha256"]))
        if row is None:
            holds.add(f"DOCUMENT_SEMANTICS_UNVERIFIED:{doc_id}")
            states[doc_id] = "NO_MATCHING_ATTESTATION"
            continue
        policy = _object(policies[doc_id], f"source contract semantic policy {doc_id}")
        verified = row["verified_at"]
        if verified > authority["issued_at"] or verified > evaluated:
            raise QualificationInputError("semantic attestation timestamps are future/inverted")
        if doc_id == GOOD_STANDING_DOCUMENT:
            _keys(
                policy,
                {"semantic_kind", "issuer", "max_issue_age_days", "max_verification_age_hours"},
                f"source contract semantic policy {doc_id}",
            )
            issued = row["issued_at"]
            if issued is None or issued > verified:
                raise QualificationInputError("Good Standing issuance timestamp is inverted")
            if row["semantic_kind"] != policy["semantic_kind"]:
                holds.add(f"DOCUMENT_SEMANTIC_KIND_MISMATCH:{doc_id}")
                states[doc_id] = "KIND_MISMATCH"
            elif row["issuer"] != policy["issuer"]:
                holds.add(f"DOCUMENT_ISSUER_MISMATCH:{doc_id}")
                states[doc_id] = "ISSUER_MISMATCH"
            elif (evaluated - issued).total_seconds() > policy["max_issue_age_days"] * 86400:
                holds.add(f"DOCUMENT_NOT_CURRENT:{doc_id}")
                states[doc_id] = "STALE_ISSUANCE"
            elif (evaluated - verified).total_seconds() > policy["max_verification_age_hours"] * 3600:
                holds.add(f"DOCUMENT_SEMANTIC_VERIFICATION_STALE:{doc_id}")
                states[doc_id] = "STALE_VERIFICATION"
            else:
                states[doc_id] = "VERIFIED_CURRENT"
        else:
            _keys(
                policy,
                {"semantic_kind", "max_verification_age_hours"},
                f"source contract semantic policy {doc_id}",
            )
            period_end = row["period_end_at"]
            if period_end is None or period_end > verified:
                raise QualificationInputError("audit period timestamp is inverted")
            if row["semantic_kind"] != policy["semantic_kind"]:
                holds.add(f"DOCUMENT_SEMANTIC_KIND_MISMATCH:{doc_id}")
                states[doc_id] = "KIND_MISMATCH"
            elif row["most_recent"] is not True:
                holds.add(f"DOCUMENT_NOT_MOST_RECENT:{doc_id}")
                states[doc_id] = "NOT_MOST_RECENT"
            elif (evaluated - verified).total_seconds() > policy["max_verification_age_hours"] * 3600:
                holds.add(f"DOCUMENT_SEMANTIC_VERIFICATION_STALE:{doc_id}")
                states[doc_id] = "STALE_VERIFICATION"
            else:
                states[doc_id] = "VERIFIED_MOST_RECENT"
    return holds, states
