"""Concept, technical-evidence, partner, and commercial validation."""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, Iterable, List, Set, Tuple
from urllib.parse import unquote, urlsplit

from . import authority_registry
from .common import (
    COMMERCIAL_STATES,
    EVIDENCE_MAX_AGE_SECONDS,
    FUTURE_SKEW_SECONDS,
    PUBLICABILITY,
    ReadinessError,
    _HEX40,
    _HEX64,
    _TOPIC_REQUIREMENTS,
    _expect_bool,
    _expect_country,
    _expect_dict,
    _expect_hex,
    _expect_id,
    _expect_int,
    _expect_list,
    _expect_str,
    _reason,
    format_time,
    parse_time,
    sha256_hex,
)

_PARTNER_KEYS = {
    "profile_id",
    "organization_label",
    "country_code",
    "topic_ids",
    "public_profile_url",
    "public_fit_summary",
    "status",
}
_PARTNER_PATH = re.compile(r"^/water4all/2026/partner-search-entry/[1-9][0-9]*$")
_CONTACT_TOKEN = re.compile(
    r"(?i)(?:mailto:|tel:|sms:|whatsapp:|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})"
)


def _required_topic_tags(topic_ids: Iterable[int]) -> Set[str]:
    required: Set[str] = set()
    for topic_id in topic_ids:
        required.update(_TOPIC_REQUIREMENTS.get(topic_id, set()))
    return required


def _retained_descriptor(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "repo_full_name": item["repo_full_name"],
        "commit_sha": item["commit_sha"],
        "path": item["path"],
        "content_sha256": item["content_sha256"],
        "publicability": item["publicability"],
        "capability_tags": item["capability_tags"],
    }


def _validate_concept_and_evidence(
    raw_concept: Any,
    raw_evidence: Any,
    evaluated_at: _dt.datetime,
    current_mode: bool,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    concept = _expect_dict(raw_concept, "$.concept")
    raw_topics = _expect_list(concept.get("topic_ids"), "$.concept.topic_ids")
    topic_ids = sorted(set(_expect_int(raw, "$.concept.topic_ids", 1) for raw in raw_topics))
    if not topic_ids or any(topic not in (1, 2, 3, 4) for topic in topic_ids):
        raise ReadinessError("topic id must be 1 through 4 and at least one topic is required")
    concept_title = _expect_str(concept.get("concept_title"), "$.concept.concept_title")
    concept_status = _expect_str(concept.get("status"), "$.concept.status")
    if concept_status != "PROPOSED_NOT_ACCEPTED":
        raise ReadinessError("concept status must remain PROPOSED_NOT_ACCEPTED in v1")

    evidence_list = _expect_list(raw_evidence, "$.technical_evidence")
    reasons: List[Dict[str, Any]] = []
    normalized_evidence: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    verified_tags: Set[str] = set()
    for index, raw in enumerate(evidence_list):
        path = "$.technical_evidence[%d]" % index
        evidence = _expect_dict(raw, path)
        evidence_id = _expect_id(evidence.get("evidence_id"), path + ".evidence_id")
        if evidence_id in seen:
            raise ReadinessError("duplicate technical evidence_id: %s" % evidence_id)
        seen.add(evidence_id)
        repo_full_name = _expect_str(evidence.get("repo_full_name"), path + ".repo_full_name")
        if repo_full_name.count("/") != 1 or repo_full_name.startswith("/") or repo_full_name.endswith("/"):
            raise ReadinessError("%s.repo_full_name must be owner/name" % path)
        commit_sha = _expect_hex(evidence.get("commit_sha"), path + ".commit_sha", _HEX40)
        content_sha256 = _expect_hex(evidence.get("content_sha256"), path + ".content_sha256", _HEX64)
        source_path = _expect_str(evidence.get("path"), path + ".path")
        if source_path.startswith("/") or ".." in source_path.split("/"):
            raise ReadinessError("%s.path must be repository-relative" % path)
        observed_dt = parse_time(evidence.get("observed_at"), path + ".observed_at")
        observed_at = format_time(observed_dt)
        verified = _expect_bool(evidence.get("verified"), path + ".verified")
        publicability = _expect_str(evidence.get("publicability"), path + ".publicability")
        if publicability not in PUBLICABILITY:
            raise ReadinessError("unsupported publicability")
        tags = sorted(set(_expect_id(raw_tag, "%s.capability_tags" % path) for raw_tag in _expect_list(evidence.get("capability_tags"), path + ".capability_tags")))
        item = {
            "evidence_id": evidence_id,
            "repo_full_name": repo_full_name,
            "commit_sha": commit_sha,
            "path": source_path,
            "content_sha256": content_sha256,
            "observed_at": observed_at,
            "verified": verified,
            "publicability": publicability,
            "capability_tags": tags,
        }
        normalized_evidence.append(item)

        retained = authority_registry.retained_evidence(evidence_id)
        retained_match = retained is not None and _retained_descriptor(item) == dict(retained)
        if retained is None:
            reasons.append(_reason("TECHNICAL_EVIDENCE_NOT_RETAINED", "technical evidence is absent from the repository-pinned manifest", [evidence_id]))
        elif not retained_match:
            reasons.append(_reason("TECHNICAL_EVIDENCE_REGISTRY_MISMATCH", "technical evidence differs from the repository-pinned descriptor", [evidence_id]))
        if observed_dt > evaluated_at + _dt.timedelta(seconds=FUTURE_SKEW_SECONDS):
            reasons.append(_reason("TECHNICAL_EVIDENCE_FUTURE", "technical evidence observation is beyond future skew", [evidence_id]))
        if current_mode and evaluated_at - observed_dt > _dt.timedelta(seconds=EVIDENCE_MAX_AGE_SECONDS):
            reasons.append(_reason("TECHNICAL_EVIDENCE_STALE", "technical evidence observation exceeds the currentness window", [evidence_id]))
        if not verified:
            reasons.append(_reason("TECHNICAL_EVIDENCE_UNVERIFIED", "caller marks the retained evidence descriptor unverified", [evidence_id]))
        if publicability != "PUBLIC_DESCRIPTOR":
            reasons.append(_reason("PUBLIC_DESCRIPTOR_REQUIRED_FOR_OWNER_REVIEW", "owner-ready technical evidence must use a public descriptor", [evidence_id]))
        if retained_match and verified and publicability == "PUBLIC_DESCRIPTOR" and observed_dt <= evaluated_at + _dt.timedelta(seconds=FUTURE_SKEW_SECONDS) and (
            not current_mode or evaluated_at - observed_dt <= _dt.timedelta(seconds=EVIDENCE_MAX_AGE_SECONDS)
        ):
            verified_tags.update(tags)

    required = _required_topic_tags(topic_ids)
    missing = sorted(required - verified_tags)
    if any(topic not in _TOPIC_REQUIREMENTS for topic in topic_ids):
        reasons.append(_reason("TOPIC_TAG_MODEL_UNSUPPORTED", "v1 has no fixed topic-tag model for one or more selected topics", [str(topic) for topic in topic_ids if topic not in _TOPIC_REQUIREMENTS]))
    if missing:
        reasons.append(_reason("TECHNICAL_TOPIC_TAG_GAPS", "required topic-tag evidence is missing", missing))

    normalized_evidence.sort(key=lambda item: item["evidence_id"])
    return {
        "concept_title": concept_title,
        "status": concept_status,
        "topic_ids": topic_ids,
        "required_capability_tags": sorted(required),
        "verified_capability_tags": sorted(verified_tags),
        "missing_capability_tags": missing,
        "evidence": normalized_evidence,
        "evidence_generation_sha256": sha256_hex(normalized_evidence),
    }, reasons


def _canonical_partner_url(value: Any, path: str) -> str:
    text = _expect_str(value, path)
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text) or "\\" in text or "%" in text:
        raise ReadinessError("%s is not a canonical public-profile URL" % path)
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise ReadinessError("%s has invalid URL authority" % path) from exc
    if parts.scheme != "https" or parts.netloc != "proposals.etag.ee" or parts.hostname != "proposals.etag.ee":
        raise ReadinessError("%s must use the canonical proposals.etag.ee HTTPS authority" % path)
    if parts.username is not None or parts.password is not None or port is not None or parts.query or parts.fragment:
        raise ReadinessError("%s must not contain userinfo, port, query, or fragment" % path)
    decoded = unquote(parts.path)
    if decoded != parts.path or "//" in decoded or "/./" in decoded or "/../" in decoded or not _PARTNER_PATH.fullmatch(decoded):
        raise ReadinessError("%s must be a canonical Water4All partner-search entry URL" % path)
    return text


def _reject_contact_route_text(value: str, path: str) -> None:
    if _CONTACT_TOKEN.search(value):
        raise ReadinessError("%s contains contact-route semantics" % path)


def _validate_partner_shortlist(raw_shortlist: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    shortlist = _expect_list(raw_shortlist, "$.partner_shortlist")
    normalized: List[Dict[str, Any]] = []
    reasons: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for index, raw in enumerate(shortlist):
        path = "$.partner_shortlist[%d]" % index
        item = _expect_dict(raw, path)
        unknown = sorted(set(item) - _PARTNER_KEYS)
        if unknown:
            raise ReadinessError("%s contains forbidden contact/outreach/secret fields: %s" % (path, ", ".join(unknown)))
        profile_id = _expect_id(item.get("profile_id"), path + ".profile_id")
        if profile_id in seen:
            raise ReadinessError("duplicate partner profile_id: %s" % profile_id)
        seen.add(profile_id)
        topics = sorted(set(_expect_int(value, path + ".topic_ids", 1) for value in _expect_list(item.get("topic_ids"), path + ".topic_ids")))
        organization_label = _expect_str(item.get("organization_label"), path + ".organization_label")
        public_fit_summary = _expect_str(item.get("public_fit_summary"), path + ".public_fit_summary")
        _reject_contact_route_text(organization_label, path + ".organization_label")
        _reject_contact_route_text(public_fit_summary, path + ".public_fit_summary")
        normalized_item = {
            "profile_id": profile_id,
            "organization_label": organization_label,
            "country_code": _expect_country(item.get("country_code"), path + ".country_code"),
            "topic_ids": topics,
            "public_profile_url": _canonical_partner_url(item.get("public_profile_url"), path + ".public_profile_url"),
            "public_fit_summary": public_fit_summary,
            "status": _expect_str(item.get("status"), path + ".status"),
        }
        if normalized_item["status"] != "RESEARCH_ONLY_NO_CONTACT_AUTHORITY":
            reasons.append(_reason("PARTNER_SHORTLIST_STATUS_INVALID", "partner profile must remain research-only without contact authority", [profile_id]))
        normalized.append(normalized_item)
    normalized.sort(key=lambda item: item["profile_id"])
    if not normalized:
        reasons.append(_reason("PARTNER_SHORTLIST_EMPTY", "no official public partner profiles are retained for owner review"))
    return normalized, reasons


def _validate_commercial(raw_commercial: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    commercial = _expect_dict(raw_commercial, "$.commercial")
    status = _expect_str(commercial.get("status"), "$.commercial.status")
    if status not in COMMERCIAL_STATES:
        raise ReadinessError("unsupported commercial status")
    normalized = {
        "status": status,
        "paid_path": _expect_str(commercial.get("paid_path"), "$.commercial.paid_path"),
        "owner_approved_internal": _expect_bool(commercial.get("owner_approved_internal"), "$.commercial.owner_approved_internal"),
        "accepted_external": _expect_bool(commercial.get("accepted_external"), "$.commercial.accepted_external"),
        "price_quote_authorized": _expect_bool(commercial.get("price_quote_authorized"), "$.commercial.price_quote_authorized"),
        "self_funding_authorized": _expect_bool(commercial.get("self_funding_authorized"), "$.commercial.self_funding_authorized"),
        "consortium_commitment_authorized": _expect_bool(commercial.get("consortium_commitment_authorized"), "$.commercial.consortium_commitment_authorized"),
    }
    reasons: List[Dict[str, Any]] = []
    if status == "PROPOSED_NOT_ACCEPTED" or not normalized["owner_approved_internal"]:
        reasons.append(_reason("COMMERCIAL_PATH_NOT_OWNER_APPROVED", "paid participation path remains proposed and not owner-approved"))
    if status == "ACCEPTED_EXTERNAL" and not normalized["accepted_external"]:
        reasons.append(_reason("COMMERCIAL_ACCEPTANCE_CONTRADICTION", "commercial status claims external acceptance without matching evidence flag"))
    return normalized, reasons
