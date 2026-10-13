from __future__ import annotations

from datetime import datetime
from typing import Any

from ._common import (
    MAX_ITEMS,
    QualificationInputError,
    _hex64,
    _id_list,
    _identifier,
    _instant,
    _keys,
    _object,
    _optional_expiry,
)

def _parse_partners(raw: Any, *, evaluated: datetime) -> dict[str, dict[str, Any]]:
    if type(raw) is not list or len(raw) > 64:
        raise QualificationInputError("partners must be a bounded array")
    partners: dict[str, dict[str, Any]] = {}
    for idx, value in enumerate(raw):
        name = f"partners[{idx}]"
        partner = _object(value, name)
        _keys(
            partner,
            {"partner_id", "commitment_status", "commitment_evidence_sha256", "observed_at", "expires_at"},
            name,
        )
        partner_id = _identifier(partner["partner_id"], f"{name}.partner_id")
        if partner_id in partners:
            raise QualificationInputError("partners contains duplicate partner_id")
        status = _identifier(partner["commitment_status"], f"{name}.commitment_status")
        if status not in {"COMMITTED", "PROSPECTIVE", "DECLINED"}:
            raise QualificationInputError("partner commitment status invalid")
        commitment_sha = partner["commitment_evidence_sha256"]
        if status == "COMMITTED":
            _hex64(commitment_sha, f"{name}.commitment_evidence_sha256")
        elif commitment_sha is not None:
            raise QualificationInputError("non-committed partner must not carry commitment evidence SHA")
        observed = _instant(partner["observed_at"], f"{name}.observed_at")
        if observed > evaluated:
            raise QualificationInputError("partner commitment evidence cannot be in the future")
        expires = _optional_expiry(partner["expires_at"], f"{name}.expires_at")
        if expires is not None and expires <= observed:
            raise QualificationInputError("partner commitment expiry must be after observation")
        effective = status
        if status == "COMMITTED" and expires is not None and expires <= evaluated:
            effective = "EXPIRED"
        partners[partner_id] = {"status": effective}
    return partners


def _parse_capability_evidence(
    raw: Any,
    *,
    bidder_id: str,
    partners: dict[str, dict[str, Any]],
    contract: dict[str, Any],
    evaluated: datetime,
) -> tuple[dict[str, list[str]], dict[str, set[str]], set[str]]:
    if type(raw) is not list or not raw or len(raw) > MAX_ITEMS:
        raise QualificationInputError("capability_evidence must be a non-empty bounded array")
    allowed = set(contract["capability_requirements"])
    providers = {bidder_id, *partners}
    evidence_ids: set[str] = set()
    coverage: dict[str, list[str]] = {cap: [] for cap in sorted(allowed)}
    uncommitted: dict[str, set[str]] = {}
    stale_caps: set[str] = set()
    for idx, value in enumerate(raw):
        name = f"capability_evidence[{idx}]"
        evidence = _object(value, name)
        _keys(
            evidence,
            {"evidence_id", "provider_id", "covers", "status", "evidence_sha256", "observed_at", "expires_at"},
            name,
        )
        evidence_id = _identifier(evidence["evidence_id"], f"{name}.evidence_id")
        if evidence_id in evidence_ids:
            raise QualificationInputError("capability_evidence contains duplicate evidence_id")
        evidence_ids.add(evidence_id)
        provider_id = _identifier(evidence["provider_id"], f"{name}.provider_id")
        if provider_id not in providers:
            raise QualificationInputError("capability evidence provider is not bidder or declared partner")
        covers = _id_list(evidence["covers"], f"{name}.covers", allow_empty=False)
        unknown = set(covers) - allowed
        if unknown:
            raise QualificationInputError(f"capability evidence covers unknown requirements: {sorted(unknown)}")
        status = _identifier(evidence["status"], f"{name}.status")
        if status not in {"VERIFIED", "PENDING", "UNAVAILABLE"}:
            raise QualificationInputError("capability evidence status invalid")
        if status == "VERIFIED":
            _hex64(evidence["evidence_sha256"], f"{name}.evidence_sha256")
        elif evidence["evidence_sha256"] is not None:
            raise QualificationInputError("non-VERIFIED capability evidence must not carry evidence SHA")
        observed = _instant(evidence["observed_at"], f"{name}.observed_at")
        if observed > evaluated:
            raise QualificationInputError("capability evidence cannot be observed in the future")
        expires = _optional_expiry(evidence["expires_at"], f"{name}.expires_at")
        if expires is not None and expires <= observed:
            raise QualificationInputError("capability evidence expiry must be after observation")
        active = status == "VERIFIED" and (expires is None or expires > evaluated)
        if status == "VERIFIED" and not active:
            stale_caps.update(covers)
        if not active:
            continue
        if provider_id != bidder_id and partners[provider_id]["status"] != "COMMITTED":
            uncommitted.setdefault(provider_id, set()).update(covers)
            continue
        for cap in covers:
            coverage[cap].append(provider_id)
    for cap in coverage:
        coverage[cap] = sorted(set(coverage[cap]))
    return coverage, uncommitted, stale_caps
