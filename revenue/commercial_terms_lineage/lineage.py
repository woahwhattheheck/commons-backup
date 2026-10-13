"""Fail-closed commercial terms / addenda decision lineage.

This module is deliberately offline.  It treats the separately retained authority
packet as the trust root for the current source + term universe and never turns a
review result into signature, submission, legal, contact, or payment authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from typing import Any, Mapping, Sequence

AUTHORITY_SCHEMA = "commercial-terms-authority/v1"
REVIEW_SCHEMA = "commercial-terms-review-input/v1"
RESULT_SCHEMA = "commercial-terms-review/v1"
MAX_FILE_BYTES = 1_000_000
MAX_ITEMS = 512
MAX_TEXT = 240
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_RE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api|access|refresh|client)[_-]?token|client[_-]?secret|password|bearer\s+[A-Za-z0-9._~-]{8,})"
)

SOURCE_ROLES = {"BASE_TERMS", "ADDENDUM", "REQUIRED_FORM", "BUYER_QA"}
CATEGORIES = {
    "PRICING_MFN",
    "PAYMENT",
    "TERM_RENEWAL",
    "INSURANCE",
    "INDEMNITY_LIABILITY",
    "CONFIDENTIALITY_PUBLIC_RECORDS",
    "DATA_SECURITY",
    "INTELLECTUAL_PROPERTY",
    "AUDIT",
    "GOVERNING_LAW_DISPUTES",
    "SUBCONTRACTING_ASSIGNMENT",
    "ACCEPTANCE_WARRANTY",
    "RECORDS_RETENTION",
    "OTHER",
}
LINEAGE = {"NEW", "CARRY_FORWARD", "REVISED"}
DECISIONS = {"ACCEPT_AS_WRITTEN", "EXCEPTION_REQUESTED", "NOT_APPLICABLE", "HOLD"}
CERT_POSTURES = {
    "NO_EXCEPTIONS_CERTIFICATION_REQUIRED",
    "EXCEPTIONS_MAY_BE_DISCLOSED",
    "TERMS_POSTURE_NOT_YET_KNOWN",
}

AUTHORITY_KEYS = {
    "schema",
    "authority_id",
    "opportunity_id",
    "source_generation",
    "previous_authority_sha256",
    "issued_at",
    "source_set_complete",
    "max_source_age_days",
    "max_decision_age_days",
    "sources",
    "terms",
    "retired_terms",
}
SOURCE_KEYS = {
    "source_id",
    "role",
    "captured_at",
    "url",
    "sha256",
    "reviewed",
    "controlling",
}
TERM_KEYS = {
    "term_id",
    "category",
    "source_id",
    "clause_sha256",
    "mandatory",
    "label",
    "lineage",
    "prior_clause_sha256",
}
RETIRED_KEYS = {"term_id", "prior_clause_sha256", "reason", "replaced_by_term_id"}
REVIEW_KEYS = {
    "schema",
    "opportunity_id",
    "source_generation",
    "certification_posture",
    "decisions",
}
DECISION_KEYS = {
    "decision_id",
    "opportunity_id",
    "source_generation",
    "term_id",
    "term_digest",
    "decision",
    "decided_at",
    "evidence_sha256",
}

AUTHORITY_CEILING = {
    "legal_advice": False,
    "buyer_or_partner_contact": False,
    "exception_request_send": False,
    "pricing_or_staffing_commitment": False,
    "certification_or_insurance_commitment": False,
    "signature": False,
    "contract_acceptance": False,
    "portal_or_submission": False,
    "spend": False,
    "payment_or_provider_mutation": False,
    "accounting_or_revenue_mutation": False,
}


class TermsLineageError(ValueError):
    """Raised for malformed or internally contradictory inputs."""


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    got = set(obj)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise TermsLineageError(f"{where}: key mismatch missing={missing} extra={extra}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TermsLineageError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    if text.startswith("\ufeff"):
        raise TermsLineageError("UTF-8 BOM is not allowed")
    try:
        return json.loads(text, object_pairs_hook=_strict_object)
    except TermsLineageError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise TermsLineageError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))


def _builtin_str(value: Any, where: str, *, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str:
        raise TermsLineageError(f"{where}: expected string")
    if not value or len(value) > max_len:
        raise TermsLineageError(f"{where}: invalid string length")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TermsLineageError(f"{where}: control character forbidden")
    if SECRET_RE.search(value):
        raise TermsLineageError(f"{where}: secret-shaped text forbidden")
    return value


def _safe_id(value: Any, where: str) -> str:
    text = _builtin_str(value, where, max_len=96)
    if not SAFE_ID_RE.fullmatch(text):
        raise TermsLineageError(f"{where}: unsafe identifier")
    return text


def _hash(value: Any, where: str) -> str:
    text = _builtin_str(value, where, max_len=64)
    if not SHA_RE.fullmatch(text):
        raise TermsLineageError(f"{where}: expected lowercase SHA-256")
    return text


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise TermsLineageError(f"{where}: expected bool")
    return value


def _int(value: Any, where: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TermsLineageError(f"{where}: invalid integer")
    return value


def _timestamp(value: Any, where: str) -> datetime:
    text = _builtin_str(value, where, max_len=32)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text):
        raise TermsLineageError(f"{where}: expected canonical UTC seconds")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise TermsLineageError(f"{where}: invalid timestamp") from exc
    return parsed


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise TermsLineageError("trusted time must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _https_url(value: Any, where: str) -> str:
    text = _builtin_str(value, where, max_len=400)
    try:
        parsed = urlsplit(text)
    except ValueError as exc:
        raise TermsLineageError(f"{where}: canonical HTTPS URL required") from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or any(ch.isspace() for ch in text)
    ):
        raise TermsLineageError(f"{where}: canonical HTTPS URL required")
    return text


def _bounded_list(value: Any, where: str) -> list[Any]:
    if type(value) is not list or len(value) > MAX_ITEMS:
        raise TermsLineageError(f"{where}: expected bounded list")
    return value


def _age_days(now: datetime, then: datetime) -> float:
    return (now - then).total_seconds() / 86400.0


def validate_authority(authority: Mapping[str, Any]) -> dict[str, Any]:
    if type(authority) is not dict:
        raise TermsLineageError("authority: expected object")
    _exact_keys(authority, AUTHORITY_KEYS, "authority")
    if authority["schema"] != AUTHORITY_SCHEMA:
        raise TermsLineageError("authority.schema: unsupported schema")
    _safe_id(authority["authority_id"], "authority.authority_id")
    _safe_id(authority["opportunity_id"], "authority.opportunity_id")
    generation = _int(authority["source_generation"], "authority.source_generation", minimum=1, maximum=1_000_000)
    previous_digest = authority["previous_authority_sha256"]
    if generation == 1:
        if previous_digest is not None:
            raise TermsLineageError("authority.previous_authority_sha256: generation 1 must be null")
    else:
        _hash(previous_digest, "authority.previous_authority_sha256")
    _timestamp(authority["issued_at"], "authority.issued_at")
    _bool(authority["source_set_complete"], "authority.source_set_complete")
    _int(authority["max_source_age_days"], "authority.max_source_age_days", minimum=1, maximum=3650)
    _int(authority["max_decision_age_days"], "authority.max_decision_age_days", minimum=1, maximum=3650)

    sources = _bounded_list(authority["sources"], "authority.sources")
    if not sources:
        raise TermsLineageError("authority.sources: at least one source required")
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        where = f"authority.sources[{index}]"
        if type(source) is not dict:
            raise TermsLineageError(f"{where}: expected object")
        _exact_keys(source, SOURCE_KEYS, where)
        sid = _safe_id(source["source_id"], f"{where}.source_id")
        if sid in source_ids:
            raise TermsLineageError(f"{where}: duplicate source_id")
        source_ids.add(sid)
        if source["role"] not in SOURCE_ROLES:
            raise TermsLineageError(f"{where}.role: unsupported role")
        _timestamp(source["captured_at"], f"{where}.captured_at")
        _https_url(source["url"], f"{where}.url")
        _hash(source["sha256"], f"{where}.sha256")
        _bool(source["reviewed"], f"{where}.reviewed")
        _bool(source["controlling"], f"{where}.controlling")

    terms = _bounded_list(authority["terms"], "authority.terms")
    if not terms:
        raise TermsLineageError("authority.terms: at least one active term required")
    term_ids: set[str] = set()
    for index, term in enumerate(terms):
        where = f"authority.terms[{index}]"
        if type(term) is not dict:
            raise TermsLineageError(f"{where}: expected object")
        _exact_keys(term, TERM_KEYS, where)
        tid = _safe_id(term["term_id"], f"{where}.term_id")
        if tid in term_ids:
            raise TermsLineageError(f"{where}: duplicate term_id")
        term_ids.add(tid)
        if term["category"] not in CATEGORIES:
            raise TermsLineageError(f"{where}.category: unsupported category")
        if term["source_id"] not in source_ids:
            raise TermsLineageError(f"{where}.source_id: unknown source")
        _hash(term["clause_sha256"], f"{where}.clause_sha256")
        _bool(term["mandatory"], f"{where}.mandatory")
        _builtin_str(term["label"], f"{where}.label", max_len=120)
        if term["lineage"] not in LINEAGE:
            raise TermsLineageError(f"{where}.lineage: unsupported lineage")
        prior = term["prior_clause_sha256"]
        if term["lineage"] == "NEW":
            if prior is not None:
                raise TermsLineageError(f"{where}.prior_clause_sha256: NEW must be null")
        else:
            _hash(prior, f"{where}.prior_clause_sha256")
        if term["lineage"] == "CARRY_FORWARD" and prior != term["clause_sha256"]:
            raise TermsLineageError(f"{where}: CARRY_FORWARD must preserve exact clause digest")
        if term["lineage"] == "REVISED" and prior == term["clause_sha256"]:
            raise TermsLineageError(f"{where}: REVISED must change clause digest")

    retired = _bounded_list(authority["retired_terms"], "authority.retired_terms")
    retired_ids: set[str] = set()
    for index, row in enumerate(retired):
        where = f"authority.retired_terms[{index}]"
        if type(row) is not dict:
            raise TermsLineageError(f"{where}: expected object")
        _exact_keys(row, RETIRED_KEYS, where)
        tid = _safe_id(row["term_id"], f"{where}.term_id")
        if tid in retired_ids or tid in term_ids:
            raise TermsLineageError(f"{where}: duplicate or still-active retired term")
        retired_ids.add(tid)
        _hash(row["prior_clause_sha256"], f"{where}.prior_clause_sha256")
        if row["reason"] not in {"BUYER_REMOVED", "REPLACED"}:
            raise TermsLineageError(f"{where}.reason: unsupported reason")
        replacement = row["replaced_by_term_id"]
        if row["reason"] == "REPLACED":
            replacement_id = _safe_id(replacement, f"{where}.replaced_by_term_id")
            if replacement_id not in term_ids:
                raise TermsLineageError(f"{where}: replacement term missing")
        elif replacement is not None:
            raise TermsLineageError(f"{where}: BUYER_REMOVED replacement must be null")
    normalized = dict(authority)
    normalized["sources"] = sorted((dict(row) for row in sources), key=lambda row: row["source_id"])
    normalized["terms"] = sorted((dict(row) for row in terms), key=lambda row: row["term_id"])
    normalized["retired_terms"] = sorted((dict(row) for row in retired), key=lambda row: row["term_id"])
    return normalized


def authority_sha256(authority: Mapping[str, Any]) -> str:
    """Return the canonical digest used to bind a retained authority generation."""
    return canonical_sha256(validate_authority(authority))


def validate_review(review: Mapping[str, Any]) -> dict[str, Any]:
    if type(review) is not dict:
        raise TermsLineageError("review: expected object")
    _exact_keys(review, REVIEW_KEYS, "review")
    if review["schema"] != REVIEW_SCHEMA:
        raise TermsLineageError("review.schema: unsupported schema")
    _safe_id(review["opportunity_id"], "review.opportunity_id")
    _int(review["source_generation"], "review.source_generation", minimum=1, maximum=1_000_000)
    if review["certification_posture"] not in CERT_POSTURES:
        raise TermsLineageError("review.certification_posture: unsupported posture")
    decisions = _bounded_list(review["decisions"], "review.decisions")
    decision_ids: set[str] = set()
    term_ids: set[str] = set()
    for index, decision in enumerate(decisions):
        where = f"review.decisions[{index}]"
        if type(decision) is not dict:
            raise TermsLineageError(f"{where}: expected object")
        _exact_keys(decision, DECISION_KEYS, where)
        did = _safe_id(decision["decision_id"], f"{where}.decision_id")
        if did in decision_ids:
            raise TermsLineageError(f"{where}: duplicate decision_id")
        decision_ids.add(did)
        _safe_id(decision["opportunity_id"], f"{where}.opportunity_id")
        _int(decision["source_generation"], f"{where}.source_generation", minimum=1, maximum=1_000_000)
        tid = _safe_id(decision["term_id"], f"{where}.term_id")
        if tid in term_ids:
            raise TermsLineageError(f"{where}: multiple decisions for term_id")
        term_ids.add(tid)
        _hash(decision["term_digest"], f"{where}.term_digest")
        if decision["decision"] not in DECISIONS:
            raise TermsLineageError(f"{where}.decision: unsupported decision")
        _timestamp(decision["decided_at"], f"{where}.decided_at")
        _hash(decision["evidence_sha256"], f"{where}.evidence_sha256")
    normalized = dict(review)
    normalized["decisions"] = sorted((dict(row) for row in decisions), key=lambda row: row["decision_id"])
    return normalized


def validate_generation_lineage(
    authority: Mapping[str, Any], previous_authority: Mapping[str, Any] | None
) -> None:
    generation = authority["source_generation"]
    if generation == 1:
        if previous_authority is not None:
            raise TermsLineageError("generation 1 must not supply previous authority")
        for term in authority["terms"]:
            if term["lineage"] != "NEW":
                raise TermsLineageError("generation 1 terms must be NEW")
        if authority["retired_terms"]:
            raise TermsLineageError("generation 1 cannot retire terms")
        return

    if previous_authority is None:
        raise TermsLineageError("previous authority required for generation > 1")
    previous_authority = validate_authority(previous_authority)
    if previous_authority["opportunity_id"] != authority["opportunity_id"]:
        raise TermsLineageError("previous authority opportunity mismatch")
    if previous_authority["source_generation"] != generation - 1:
        raise TermsLineageError("previous authority generation must be exactly current-1")
    if authority_sha256(previous_authority) != authority["previous_authority_sha256"]:
        raise TermsLineageError("previous authority digest mismatch")

    previous_terms = {row["term_id"]: row for row in previous_authority["terms"]}
    current_terms = {row["term_id"]: row for row in authority["terms"]}
    retired = {row["term_id"]: row for row in authority["retired_terms"]}

    for tid, current in current_terms.items():
        previous = previous_terms.get(tid)
        if previous is None:
            if current["lineage"] != "NEW" or current["prior_clause_sha256"] is not None:
                raise TermsLineageError(f"term {tid}: new identity must be NEW")
            continue
        if current["clause_sha256"] == previous["clause_sha256"]:
            if current["category"] != previous["category"] or current["mandatory"] != previous["mandatory"]:
                raise TermsLineageError(f"term {tid}: semantic classification changed without clause digest change")
            if current["lineage"] != "CARRY_FORWARD" or current["prior_clause_sha256"] != previous["clause_sha256"]:
                raise TermsLineageError(f"term {tid}: unchanged term lacks exact carry-forward lineage")
        else:
            if current["lineage"] != "REVISED" or current["prior_clause_sha256"] != previous["clause_sha256"]:
                raise TermsLineageError(f"term {tid}: changed term lacks exact revision lineage")

    for tid, previous in previous_terms.items():
        if tid in current_terms:
            continue
        row = retired.get(tid)
        if row is None:
            raise TermsLineageError(f"term {tid}: disappeared without explicit retirement")
        if row["prior_clause_sha256"] != previous["clause_sha256"]:
            raise TermsLineageError(f"term {tid}: retirement digest mismatch")

    extra_retired = set(retired) - set(previous_terms)
    if extra_retired:
        raise TermsLineageError(f"retired terms not present in prior generation: {sorted(extra_retired)}")


def _decision_projection(
    term: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    authority: Mapping[str, Any],
    as_of: datetime,
) -> tuple[str, str | None, str | None]:
    if decision is None:
        return "OWNER_DECISION_REQUIRED", None, None
    if decision["opportunity_id"] != authority["opportunity_id"]:
        raise TermsLineageError(f"decision {decision['decision_id']}: cross-opportunity transplant")
    if decision["term_digest"] != term["clause_sha256"]:
        return "OWNER_DECISION_REQUIRED", decision["decision_id"], "STALE_TERM_DIGEST"
    generation = authority["source_generation"]
    decision_generation = decision["source_generation"]
    if decision_generation == generation:
        pass
    elif decision_generation == generation - 1 and term["lineage"] == "CARRY_FORWARD":
        pass
    else:
        return "OWNER_DECISION_REQUIRED", decision["decision_id"], "STALE_SOURCE_GENERATION"
    decided_at = _timestamp(decision["decided_at"], "decision.decided_at")
    if decided_at > as_of:
        return "HOLD", decision["decision_id"], "FUTURE_DECISION"
    max_age = authority["max_decision_age_days"]
    if _age_days(as_of, decided_at) > max_age:
        return "OWNER_DECISION_REQUIRED", decision["decision_id"], "STALE_DECISION"
    if decision_generation == generation:
        issued_at = _timestamp(authority["issued_at"], "authority.issued_at")
        if decided_at < issued_at:
            return "OWNER_DECISION_REQUIRED", decision["decision_id"], "DECISION_PREDATES_AUTHORITY"
    return str(decision["decision"]), decision["decision_id"], None


def compile_review(
    authority: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    as_of: datetime,
    previous_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    authority = validate_authority(authority)
    review = validate_review(review)
    previous_authority = validate_authority(previous_authority) if previous_authority is not None else None
    validate_generation_lineage(authority, previous_authority)
    as_of = as_of.astimezone(timezone.utc).replace(microsecond=0)

    if review["opportunity_id"] != authority["opportunity_id"]:
        raise TermsLineageError("review opportunity does not match authority")
    if review["source_generation"] != authority["source_generation"]:
        raise TermsLineageError("review source generation does not match authority")

    issued_at = _timestamp(authority["issued_at"], "authority.issued_at")
    source_reasons: list[str] = []
    if issued_at > as_of:
        source_reasons.append("FUTURE_AUTHORITY")
    if not authority["source_set_complete"]:
        source_reasons.append("SOURCE_SET_INCOMPLETE")
    for source in authority["sources"]:
        captured = _timestamp(source["captured_at"], f"source {source['source_id']} captured_at")
        if captured > as_of:
            source_reasons.append(f"FUTURE_SOURCE:{source['source_id']}")
        if source["controlling"] and not source["reviewed"]:
            source_reasons.append(f"CONTROLLING_SOURCE_UNREVIEWED:{source['source_id']}")
        if source["controlling"] and _age_days(as_of, captured) > authority["max_source_age_days"]:
            source_reasons.append(f"CONTROLLING_SOURCE_STALE:{source['source_id']}")

    decisions_by_term = {row["term_id"]: row for row in review["decisions"]}
    active_ids = {row["term_id"] for row in authority["terms"]}
    unknown_decisions = sorted(set(decisions_by_term) - active_ids)
    if unknown_decisions:
        raise TermsLineageError(f"decisions reference non-active terms: {unknown_decisions}")

    term_rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    holds: list[str] = []
    exceptions: list[dict[str, str]] = []
    for term in sorted(authority["terms"], key=lambda row: row["term_id"]):
        disposition, decision_id, reason = _decision_projection(
            term, decisions_by_term.get(term["term_id"]), authority, as_of
        )
        row = {
            "term_id": term["term_id"],
            "category": term["category"],
            "mandatory": term["mandatory"],
            "source_id": term["source_id"],
            "clause_sha256": term["clause_sha256"],
            "lineage": term["lineage"],
            "disposition": disposition,
            "decision_id": decision_id,
            "coverage_reason": reason,
        }
        term_rows.append(row)
        if disposition == "OWNER_DECISION_REQUIRED":
            unresolved.append(term["term_id"])
        elif disposition == "HOLD":
            holds.append(term["term_id"])
        elif disposition == "EXCEPTION_REQUESTED":
            decision = decisions_by_term[term["term_id"]]
            exceptions.append(
                {
                    "term_id": term["term_id"],
                    "term_digest": term["clause_sha256"],
                    "decision_id": decision["decision_id"],
                    "evidence_sha256": decision["evidence_sha256"],
                }
            )

    posture = review["certification_posture"]
    mandatory_exception = any(
        row["mandatory"] and row["disposition"] == "EXCEPTION_REQUESTED" for row in term_rows
    )
    mandatory_unresolved = any(
        row["mandatory"] and row["disposition"] in {"OWNER_DECISION_REQUIRED", "HOLD"}
        for row in term_rows
    )

    reasons: list[str] = []
    if source_reasons:
        state = "SOURCE_REFRESH_REQUIRED"
        reasons.extend(sorted(set(source_reasons)))
    elif holds:
        state = "HOLD"
        reasons.extend(f"TERM_HOLD:{tid}" for tid in sorted(holds))
    elif posture == "TERMS_POSTURE_NOT_YET_KNOWN":
        state = "OWNER_DECISION_REQUIRED"
        reasons.append("CERTIFICATION_POSTURE_UNKNOWN")
    elif posture == "NO_EXCEPTIONS_CERTIFICATION_REQUIRED" and exceptions:
        state = "CONFLICT"
        reasons.append("NO_EXCEPTIONS_CERTIFICATION_CONFLICT")
    elif mandatory_unresolved or unresolved:
        state = "OWNER_DECISION_REQUIRED"
        reasons.extend(f"TERM_DECISION_REQUIRED:{tid}" for tid in sorted(unresolved))
    elif posture == "EXCEPTIONS_MAY_BE_DISCLOSED" and exceptions:
        state = "EXCEPTION_DISCLOSURE_REQUIRED"
        reasons.append("EXCEPTION_MANIFEST_REQUIRED")
    elif mandatory_exception:
        state = "OWNER_DECISION_REQUIRED"
        reasons.append("MANDATORY_EXCEPTION_REQUIRES_OWNER_REVIEW")
    else:
        state = "TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW"
        reasons.append("ALL_ACTIVE_TERMS_COVERED")

    result_core = {
        "schema": RESULT_SCHEMA,
        "opportunity_id": authority["opportunity_id"],
        "source_generation": authority["source_generation"],
        "compiled_at": iso_utc(as_of),
        "state": state,
        "reasons": reasons,
        "authority_sha256": canonical_sha256(authority),
        "previous_authority_sha256": (
            canonical_sha256(previous_authority) if previous_authority is not None else None
        ),
        "review_input_sha256": canonical_sha256(review),
        "certification_posture": posture,
        "active_terms": term_rows,
        "exception_manifest": sorted(exceptions, key=lambda row: row["term_id"]),
        "retired_terms": sorted(
            [
                {
                    "term_id": row["term_id"],
                    "prior_clause_sha256": row["prior_clause_sha256"],
                    "reason": row["reason"],
                    "replaced_by_term_id": row["replaced_by_term_id"],
                }
                for row in authority["retired_terms"]
            ],
            key=lambda row: row["term_id"],
        ),
        "authority_ceiling": AUTHORITY_CEILING,
    }
    result = dict(result_core)
    result["receipt_sha256"] = canonical_sha256(result_core)
    return result


def verify_review(
    authority: Mapping[str, Any],
    review: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    previous_authority: Mapping[str, Any] | None = None,
    trusted_now: datetime | None = None,
) -> dict[str, Any]:
    if type(receipt) is not dict:
        raise TermsLineageError("receipt: expected object")
    if receipt.get("schema") != RESULT_SCHEMA:
        raise TermsLineageError("receipt: unsupported schema")
    compiled_at = _timestamp(receipt.get("compiled_at"), "receipt.compiled_at")
    now = (trusted_now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if compiled_at > now.replace(microsecond=0):
        raise TermsLineageError("receipt compiled_at is in the future")
    expected = compile_review(
        authority,
        review,
        as_of=compiled_at,
        previous_authority=previous_authority,
    )
    if canonical_bytes(receipt) != canonical_bytes(expected):
        raise TermsLineageError("receipt does not recompile byte-identically")
    return expected


def render_markdown(receipt: Mapping[str, Any]) -> str:
    if receipt.get("schema") != RESULT_SCHEMA:
        raise TermsLineageError("receipt: unsupported schema")
    lines = [
        "# Commercial Terms Exception Lineage",
        "",
        f"- Opportunity: `{receipt['opportunity_id']}`",
        f"- Source generation: `{receipt['source_generation']}`",
        f"- Compiled at: `{receipt['compiled_at']}`",
        f"- State: **{receipt['state']}**",
        f"- Certification posture: `{receipt['certification_posture']}`",
        f"- Receipt SHA-256: `{receipt['receipt_sha256']}`",
        "",
        "## Active terms",
        "",
        "| Term | Category | Mandatory | Lineage | Disposition |",
        "|---|---|---:|---|---|",
    ]
    for row in receipt["active_terms"]:
        lines.append(
            f"| `{row['term_id']}` | `{row['category']}` | {str(row['mandatory']).lower()} | `{row['lineage']}` | `{row['disposition']}` |"
        )
    lines.extend(["", "## Exceptions", ""])
    if receipt["exception_manifest"]:
        for row in receipt["exception_manifest"]:
            lines.append(
                f"- `{row['term_id']}` — decision `{row['decision_id']}`; term `{row['term_digest']}`"
            )
    else:
        lines.append("- None in the verified input.")
    lines.extend(["", "## Reasons", ""])
    lines.extend(f"- `{reason}`" for reason in receipt["reasons"])
    lines.extend(
        [
            "",
            "## Authority ceiling",
            "",
            "This artifact is offline owner-review decision support only. It does not authorize legal advice, buyer/partner contact, exception transmission, commitments, signature, contract acceptance, portal action, submission, spend, payment/provider mutation, accounting action, or revenue recognition.",
            "",
        ]
    )
    return "\n".join(lines)


def read_json_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_FILE_BYTES) -> Any:
    p = Path(path)
    try:
        info = os.lstat(p)
    except OSError as exc:
        raise TermsLineageError(f"cannot stat input: {p}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise TermsLineageError("input must be an ordinary non-symlink file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise TermsLineageError("input changed to non-regular file")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes or os.read(fd, 1):
            raise TermsLineageError("input exceeds byte limit")
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TermsLineageError("input must be strict UTF-8") from exc
    return loads_strict(text)


def write_exclusive(path: str | os.PathLike[str], content: str) -> None:
    p = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(p, flags, 0o600)
    except FileExistsError as exc:
        raise TermsLineageError(f"refusing to overwrite output: {p}") from exc
    except OSError as exc:
        raise TermsLineageError(f"cannot create output: {p}") from exc
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
