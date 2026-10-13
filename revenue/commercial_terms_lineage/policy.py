"""Production-current policy guard for commercial terms lineage.

`lineage.py` is the deterministic historical engine. This module is the stricter
current-readiness policy boundary: it rejects ambiguous/replayed decision evidence,
requires monotone source-generation custody, and ensures every source that supplies
an active term is reviewed and fresh before a current green state can be emitted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

try:
    from .lineage import (
        TermsLineageError,
        canonical_sha256,
        compile_review as _compile_review,
        validate_authority as _validate_authority,
        validate_generation_lineage,
        validate_review as _validate_review,
    )
except ImportError:  # direct execution/tests from package directory
    from lineage import (  # type: ignore
        TermsLineageError,
        canonical_sha256,
        compile_review as _compile_review,
        validate_authority as _validate_authority,
        validate_generation_lineage,
        validate_review as _validate_review,
    )


def _timestamp(value: str, where: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise TermsLineageError(f"{where}: invalid canonical UTC timestamp") from exc
    return parsed


def _age_days(now: datetime, then: datetime) -> float:
    return (now - then).total_seconds() / 86400.0


def validate_review(review: Mapping[str, Any]) -> dict[str, Any]:
    """Validate review shape plus one-evidence-record/one-decision identity.

    A SHA-256 identifies one immutable evidence artifact. Reusing that same artifact
    as evidence for distinct decisions lets a caller relabel proof across terms, so
    production-current review rejects any digest replay across decision identities.
    """
    normalized = _validate_review(review)
    evidence_owner: dict[str, str] = {}
    for row in normalized["decisions"]:
        digest = row["evidence_sha256"]
        previous = evidence_owner.get(digest)
        if previous is not None and previous != row["decision_id"]:
            raise TermsLineageError(
                "review decision evidence replay: "
                f"evidence_sha256 {digest} reused by {previous} and {row['decision_id']}"
            )
        evidence_owner[digest] = row["decision_id"]
    return normalized


def validate_current_inputs(
    authority: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    as_of: datetime,
    previous_authority: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """Validate invariants that must hold for a production-current assessment."""
    auth = _validate_authority(authority)
    current_review = validate_review(review)
    previous = _validate_authority(previous_authority) if previous_authority is not None else None
    validate_generation_lineage(auth, previous)

    now = as_of.astimezone(timezone.utc).replace(microsecond=0)
    issued_at = _timestamp(auth["issued_at"], "authority.issued_at")
    if previous is not None:
        previous_issued = _timestamp(previous["issued_at"], "previous_authority.issued_at")
        if issued_at < previous_issued:
            raise TermsLineageError("authority issuance regressed behind previous generation")

    sources = {row["source_id"]: row for row in auth["sources"]}
    for source in auth["sources"]:
        captured = _timestamp(source["captured_at"], f"source {source['source_id']} captured_at")
        if captured > issued_at:
            raise TermsLineageError(
                f"source {source['source_id']} was captured after authority issuance"
            )

    terms = {row["term_id"]: row for row in auth["terms"]}
    for decision in current_review["decisions"]:
        if decision["source_generation"] != auth["source_generation"]:
            continue
        term = terms.get(decision["term_id"])
        if term is None:
            continue
        captured = _timestamp(
            sources[term["source_id"]]["captured_at"],
            f"source {term['source_id']} captured_at",
        )
        decided = _timestamp(decision["decided_at"], f"decision {decision['decision_id']} decided_at")
        if decided < max(issued_at, captured):
            raise TermsLineageError(
                f"decision {decision['decision_id']} predates authoritative source-generation custody"
            )
        if decided > now:
            # The deterministic engine renders this HOLD. Leave state construction
            # to it instead of turning a future decision into an input-shape error.
            continue

    return auth, current_review, previous


def compile_current_state(
    authority: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    as_of: datetime,
    previous_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a production-current receipt under the strict policy boundary."""
    now = as_of.astimezone(timezone.utc).replace(microsecond=0)
    auth, current_review, previous = validate_current_inputs(
        authority,
        review,
        as_of=now,
        previous_authority=previous_authority,
    )
    receipt = _compile_review(
        auth,
        current_review,
        as_of=now,
        previous_authority=previous,
    )

    active_source_ids = {term["source_id"] for term in auth["terms"]}
    extra_source_reasons: list[str] = []
    for source in auth["sources"]:
        if source["source_id"] not in active_source_ids:
            continue
        captured = _timestamp(source["captured_at"], f"source {source['source_id']} captured_at")
        if not source["reviewed"]:
            extra_source_reasons.append(f"ACTIVE_TERM_SOURCE_UNREVIEWED:{source['source_id']}")
        if _age_days(now, captured) > auth["max_source_age_days"]:
            extra_source_reasons.append(f"ACTIVE_TERM_SOURCE_STALE:{source['source_id']}")

    if extra_source_reasons:
        prior_source_reasons = receipt["reasons"] if receipt["state"] == "SOURCE_REFRESH_REQUIRED" else []
        receipt["state"] = "SOURCE_REFRESH_REQUIRED"
        receipt["reasons"] = sorted(set(prior_source_reasons + extra_source_reasons))
        core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = canonical_sha256(core)

    return receipt
