from __future__ import annotations

from datetime import datetime
from typing import Any

from ._common import (
    SOURCE_MAX_AGE_SECONDS,
    QualificationInputError,
    _bool,
    _hex64,
    _identifier,
    _instant,
    _keys,
    _object,
    _optional_expiry,
)

def _parse_source_capture(
    raw: Any,
    *,
    contract: dict[str, Any],
    evaluated: datetime,
    expected_rfp_sha256: str,
) -> tuple[dict[str, Any], set[str]]:
    source = _object(raw, "source_capture")
    _keys(
        source,
        {
            "bid_id",
            "document_url",
            "document_sha256",
            "captured_at",
            "updates_checked_at",
            "addenda_complete",
            "questions_answers_complete",
        },
        "source_capture",
    )
    if source["bid_id"] != contract["bid_id"]:
        raise QualificationInputError("source_capture.bid_id does not match compiled RFP")
    if source["document_url"] != contract["official_rfp_url"]:
        raise QualificationInputError("source_capture.document_url does not match compiled RFP")
    document_sha = _hex64(source["document_sha256"], "source_capture.document_sha256")
    expected_sha = _hex64(expected_rfp_sha256, "expected_rfp_sha256")
    captured = _instant(source["captured_at"], "source_capture.captured_at")
    checked = _instant(source["updates_checked_at"], "source_capture.updates_checked_at")
    if captured > evaluated or checked > evaluated:
        raise QualificationInputError("source capture/update check cannot be in the future")
    if checked < captured:
        raise QualificationInputError("updates_checked_at cannot predate captured_at")
    addenda_complete = _bool(source["addenda_complete"], "source_capture.addenda_complete")
    qa_complete = _bool(
        source["questions_answers_complete"],
        "source_capture.questions_answers_complete",
    )
    holds: set[str] = set()
    if document_sha != expected_sha:
        holds.add("RFP_SHA256_MISMATCH")
    if not addenda_complete:
        holds.add("RFP_UPDATES_NOT_CONFIRMED_COMPLETE")
    if (evaluated - checked).total_seconds() > SOURCE_MAX_AGE_SECONDS:
        holds.add("RFP_UPDATE_CHECK_STALE")
    qa_due = _instant(contract["qa_posted_by_at"], "source contract qa_posted_by_at")
    if evaluated >= qa_due and not qa_complete:
        holds.add("RFP_QA_NOT_CONFIRMED_COMPLETE")
    return {
        "document_sha256": document_sha,
        "captured_at": captured,
        "updates_checked_at": checked,
        "updates_checked_at_text": source["updates_checked_at"],
        "addenda_complete": addenda_complete,
        "questions_answers_complete": qa_complete,
    }, holds


def _parse_documents(
    raw: Any,
    *,
    contract: dict[str, Any],
    evaluated: datetime,
) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, str]]:
    docs = _object(raw, "bidder.documents")
    expected = set(contract["mandatory_document_requirements"])
    if set(docs) != expected:
        raise QualificationInputError(
            "bidder.documents must cover exact mandatory document set; "
            f"missing={sorted(expected - set(docs))}, extra={sorted(set(docs) - expected)}"
        )
    parsed: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    states: dict[str, str] = {}
    for doc_id in sorted(expected):
        name = f"bidder.documents.{doc_id}"
        item = _object(docs[doc_id], name)
        _keys(item, {"status", "evidence_sha256", "observed_at", "expires_at"}, name)
        status = _identifier(item["status"], f"{name}.status")
        if status not in {"READY", "PENDING", "MISSING"}:
            raise QualificationInputError(f"{name}.status invalid")
        evidence_sha = item["evidence_sha256"]
        if status == "READY":
            evidence_sha = _hex64(evidence_sha, f"{name}.evidence_sha256")
        elif evidence_sha is not None:
            raise QualificationInputError(f"{name}.evidence_sha256 must be null unless READY")
        observed = _instant(item["observed_at"], f"{name}.observed_at")
        if observed > evaluated:
            raise QualificationInputError(f"{name}.observed_at is in the future")
        expires = _optional_expiry(item["expires_at"], f"{name}.expires_at")
        if expires is not None and expires <= observed:
            raise QualificationInputError(f"{name}.expires_at must be after observed_at")
        effective = status
        if status == "READY" and expires is not None and expires <= evaluated:
            effective = "EXPIRED"
        if effective != "READY":
            missing.append(doc_id)
        states[doc_id] = effective
        parsed[doc_id] = {
            "status": effective,
            "evidence_sha256": evidence_sha,
            "observed_at": observed,
            "expires_at": expires,
        }
    return parsed, missing, states
