"""Fail-closed partner qualification for public-sector teaming decisions.

This module is intentionally local and read-only with respect to providers and buyers.
It turns structured requirements plus source-linked evidence into deterministic human-
review packets. Commercial authority fields remain false for eligibility assertion,
outreach, quoting, bid submission, provider mutation, and payment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ALLOWED_REQUIREMENT_CATEGORIES = {
    "authority",
    "capability",
    "certification",
    "experience",
    "geography",
    "insurance",
    "registration",
}
ALLOWED_EVIDENCE_STATES = {"confirmed", "contradicted", "claimed", "unknown"}
SATISFYING_EVIDENCE_STATES = {"confirmed"}
FINAL_STATUSES = {
    "READY_FOR_HUMAN_REVIEW",
    "QUALIFICATION_GAPS",
    "DISQUALIFYING_CONTRADICTION",
}


class QualificationError(ValueError):
    """Raised when qualification inputs are malformed or ambiguous."""


@dataclass(frozen=True)
class RequirementResult:
    requirement_id: str
    category: str
    description: str
    must_have: bool
    status: str
    evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{field} must be a non-empty string")
    return value.strip()


def _parse_date(value: Any, field: str) -> date:
    raw = _require_nonempty_string(value, field)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise QualificationError(f"{field} must be ISO date YYYY-MM-DD") from exc


def _validate_source(evidence: Mapping[str, Any], evidence_id: str) -> str:
    source = evidence.get("source")
    if not isinstance(source, Mapping):
        raise QualificationError(f"evidence {evidence_id}: source must be an object")
    return _require_nonempty_string(source.get("ref"), f"evidence {evidence_id}.source.ref")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_unique_ids(items: Sequence[Mapping[str, Any]], field: str) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise QualificationError(f"{field}[{index}] must be an object")
        item_id = _require_nonempty_string(item.get("id"), f"{field}[{index}].id")
        if item_id in seen:
            raise QualificationError(f"duplicate {field} id: {item_id}")
        seen.add(item_id)


def _normalise_requirements(opportunity: Mapping[str, Any]) -> list[dict[str, Any]]:
    requirements = opportunity.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise QualificationError("opportunity.requirements must be a non-empty list")
    _validate_unique_ids(requirements, "requirements")
    normalised: list[dict[str, Any]] = []
    for item in requirements:
        requirement_id = _require_nonempty_string(item.get("id"), "requirement.id")
        category = _require_nonempty_string(item.get("category"), f"requirement {requirement_id}.category")
        if category not in ALLOWED_REQUIREMENT_CATEGORIES:
            raise QualificationError(
                f"requirement {requirement_id}: category must be one of "
                + ", ".join(sorted(ALLOWED_REQUIREMENT_CATEGORIES))
            )
        must_have = item.get("must_have", True)
        if not isinstance(must_have, bool):
            raise QualificationError(f"requirement {requirement_id}.must_have must be boolean")
        description = _require_nonempty_string(
            item.get("description"), f"requirement {requirement_id}.description"
        )
        normalised.append(
            {
                "id": requirement_id,
                "category": category,
                "must_have": must_have,
                "description": description,
            }
        )
    return sorted(normalised, key=lambda item: item["id"])


def _normalise_evidence(partner: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = partner.get("evidence", [])
    if not isinstance(evidence, list):
        raise QualificationError("partner.evidence must be a list")
    _validate_unique_ids(evidence, "evidence")
    normalised: list[dict[str, Any]] = []
    for item in evidence:
        evidence_id = _require_nonempty_string(item.get("id"), "evidence.id")
        requirement_id = _require_nonempty_string(
            item.get("requirement_id"), f"evidence {evidence_id}.requirement_id"
        )
        state = _require_nonempty_string(item.get("state"), f"evidence {evidence_id}.state")
        if state not in ALLOWED_EVIDENCE_STATES:
            raise QualificationError(
                f"evidence {evidence_id}: state must be one of "
                + ", ".join(sorted(ALLOWED_EVIDENCE_STATES))
            )
        source_ref = _validate_source(item, evidence_id)
        observed_on = _parse_date(item.get("observed_on"), f"evidence {evidence_id}.observed_on")
        expires_on_raw = item.get("expires_on")
        expires_on = (
            _parse_date(expires_on_raw, f"evidence {evidence_id}.expires_on")
            if expires_on_raw is not None
            else None
        )
        normalised.append(
            {
                "id": evidence_id,
                "requirement_id": requirement_id,
                "state": state,
                "source_ref": source_ref,
                "observed_on": observed_on,
                "expires_on": expires_on,
                "note": str(item.get("note", "")).strip(),
            }
        )
    return sorted(normalised, key=lambda item: item["id"])


def _result_for_requirement(
    requirement: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]], as_of: date
) -> RequirementResult:
    linked = sorted(
        (item for item in evidence if item["requirement_id"] == requirement["id"]),
        key=lambda item: item["id"],
    )
    ids = tuple(item["id"] for item in linked)
    base = (
        requirement["id"],
        requirement["category"],
        requirement["description"],
        requirement["must_have"],
    )
    if not linked:
        return RequirementResult(*base, "GAP", (), ("NO_EVIDENCE",))

    contradictions = [item for item in linked if item["state"] == "contradicted"]
    if contradictions:
        return RequirementResult(
            *base,
            "CONTRADICTED",
            ids,
            tuple(f"CONTRADICTED:{item['id']}" for item in contradictions),
        )

    confirmed = [item for item in linked if item["state"] in SATISFYING_EVIDENCE_STATES]
    if not confirmed:
        states = sorted({item["state"] for item in linked})
        return RequirementResult(
            *base,
            "UNVERIFIED",
            ids,
            tuple(f"NON_SATISFYING_STATE:{state}" for state in states),
        )

    live_confirmed = [
        item for item in confirmed if item["expires_on"] is None or item["expires_on"] >= as_of
    ]
    if not live_confirmed:
        return RequirementResult(
            *base,
            "STALE",
            ids,
            tuple(f"EXPIRED:{item['id']}:{item['expires_on'].isoformat()}" for item in confirmed),
        )

    usable = [item for item in live_confirmed if item["observed_on"] <= as_of]
    if not usable:
        future = [item for item in live_confirmed if item["observed_on"] > as_of]
        return RequirementResult(
            *base,
            "UNVERIFIED",
            ids,
            tuple(f"FUTURE_OBSERVATION:{item['id']}" for item in future),
        )

    return RequirementResult(*base, "SATISFIED", ids, ())


def _authority_boundary() -> dict[str, bool]:
    return {
        "eligibility_asserted": False,
        "outreach_authorized": False,
        "quote_authorized": False,
        "bid_submission_authorized": False,
        "provider_mutation_authorized": False,
        "payment_authorized": False,
    }


def evaluate_partner(
    opportunity: Mapping[str, Any], partner: Mapping[str, Any], *, as_of: str
) -> dict[str, Any]:
    """Evaluate one partner against source-linked opportunity requirements.

    The returned status is a triage result for human review only. It is deliberately
    not an eligibility assertion or authorization to contact, quote, bid, or submit.
    """

    if not isinstance(opportunity, Mapping) or not isinstance(partner, Mapping):
        raise QualificationError("opportunity and partner must be objects")
    as_of_date = _parse_date(as_of, "as_of")
    opportunity_id = _require_nonempty_string(opportunity.get("id"), "opportunity.id")
    partner_id = _require_nonempty_string(partner.get("id"), "partner.id")
    requirements = _normalise_requirements(opportunity)
    evidence = _normalise_evidence(partner)
    known_requirement_ids = {item["id"] for item in requirements}
    unknown_links = sorted(
        item["id"] for item in evidence if item["requirement_id"] not in known_requirement_ids
    )
    if unknown_links:
        raise QualificationError(
            "evidence references unknown requirement ids: " + ", ".join(unknown_links)
        )

    results = [_result_for_requirement(req, evidence, as_of_date) for req in requirements]
    must_results = [result for result in results if result.must_have]
    if any(result.status == "CONTRADICTED" for result in must_results):
        overall = "DISQUALIFYING_CONTRADICTION"
    elif any(result.status != "SATISFIED" for result in must_results):
        overall = "QUALIFICATION_GAPS"
    else:
        overall = "READY_FOR_HUMAN_REVIEW"

    evidence_export = [
        {
            "id": item["id"],
            "requirement_id": item["requirement_id"],
            "state": item["state"],
            "source_ref": item["source_ref"],
            "observed_on": item["observed_on"].isoformat(),
            "expires_on": item["expires_on"].isoformat() if item["expires_on"] else None,
            "note": item["note"],
        }
        for item in evidence
    ]
    requirement_export = [
        {
            "id": item["id"],
            "category": item["category"],
            "must_have": item["must_have"],
            "description": item["description"],
        }
        for item in requirements
    ]
    result_export = [
        {
            "requirement_id": item.requirement_id,
            "category": item.category,
            "description": item.description,
            "must_have": item.must_have,
            "status": item.status,
            "evidence_ids": list(item.evidence_ids),
            "reasons": list(item.reasons),
        }
        for item in results
    ]
    digest_input = {
        "as_of": as_of_date.isoformat(),
        "opportunity_id": opportunity_id,
        "partner_id": partner_id,
        "requirements": requirement_export,
        "evidence": evidence_export,
    }
    return {
        "schema_version": 1,
        "opportunity_id": opportunity_id,
        "partner_id": partner_id,
        "as_of": as_of_date.isoformat(),
        "status": overall,
        "requirements": result_export,
        "evidence": evidence_export,
        "counts": {
            "must_have": len(must_results),
            "satisfied_must_have": sum(item.status == "SATISFIED" for item in must_results),
            "gaps": sum(item.status in {"GAP", "UNVERIFIED", "STALE"} for item in results),
            "contradictions": sum(item.status == "CONTRADICTED" for item in results),
        },
        "source_refs": sorted({item["source_ref"] for item in evidence_export}),
        "packet_sha256": _sha256(digest_input),
        "authority": _authority_boundary(),
    }


def evaluate_room(
    opportunity: Mapping[str, Any], partners: Sequence[Mapping[str, Any]], *, as_of: str
) -> dict[str, Any]:
    """Evaluate multiple partners without ranking or inventing a winner."""

    if not isinstance(partners, Sequence) or isinstance(partners, (str, bytes)) or not partners:
        raise QualificationError("partners must be a non-empty list")
    _validate_unique_ids(partners, "partners")
    packets = sorted(
        (evaluate_partner(opportunity, partner, as_of=as_of) for partner in partners),
        key=lambda packet: packet["partner_id"],
    )
    status_counts = {status: 0 for status in sorted(FINAL_STATUSES)}
    for packet in packets:
        status_counts[packet["status"]] += 1
    digest_input = [
        {"partner_id": packet["partner_id"], "packet_sha256": packet["packet_sha256"]}
        for packet in packets
    ]
    return {
        "schema_version": 1,
        "opportunity_id": packets[0]["opportunity_id"],
        "as_of": packets[0]["as_of"],
        "status_counts": status_counts,
        "partners": packets,
        "room_sha256": _sha256(digest_input),
        "authority": _authority_boundary(),
    }


def _md_cell(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def export_human_review_markdown(packet: Mapping[str, Any]) -> str:
    """Render one buyer-neutral review packet without adding factual claims."""

    status = _require_nonempty_string(packet.get("status"), "packet.status")
    opportunity_id = _require_nonempty_string(packet.get("opportunity_id"), "packet.opportunity_id")
    partner_id = _require_nonempty_string(packet.get("partner_id"), "packet.partner_id")
    digest = _require_nonempty_string(packet.get("packet_sha256"), "packet.packet_sha256")
    requirements = packet.get("requirements")
    evidence = packet.get("evidence")
    if not isinstance(requirements, list):
        raise QualificationError("packet.requirements must be a list")
    if not isinstance(evidence, list):
        raise QualificationError("packet.evidence must be a list")

    lines = [
        "# Partner qualification review packet",
        "",
        f"- Opportunity: `{_md_cell(opportunity_id)}`",
        f"- Partner: `{_md_cell(partner_id)}`",
        f"- Triage status: **{_md_cell(status)}**",
        f"- Evidence packet SHA-256: `{_md_cell(digest)}`",
        "",
        "> Human review only. Authority: eligibility_asserted=false; outreach_authorized=false; quote_authorized=false; bid_submission_authorized=false; provider_mutation_authorized=false; payment_authorized=false.",
        "",
        "## Requirement matrix",
        "",
        "| Requirement | Description | Category | Required | Status | Evidence | Reasons |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in requirements:
        if not isinstance(item, Mapping):
            raise QualificationError("packet requirement entries must be objects")
        evidence_ids = ", ".join(_md_cell(v) for v in item.get("evidence_ids", [])) or "—"
        reasons = ", ".join(_md_cell(v) for v in item.get("reasons", [])) or "—"
        lines.append(
            "| {rid} | {description} | {category} | {required} | {status} | {evidence} | {reasons} |".format(
                rid=_md_cell(item.get("requirement_id", "")),
                description=_md_cell(item.get("description", "")),
                category=_md_cell(item.get("category", "")),
                required="yes" if item.get("must_have") else "no",
                status=_md_cell(item.get("status", "")),
                evidence=evidence_ids,
                reasons=reasons,
            )
        )

    lines.extend(
        [
            "",
            "## Evidence ledger",
            "",
            "| Evidence | Requirement | State | Source | Observed | Expires | Note |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in evidence:
        if not isinstance(item, Mapping):
            raise QualificationError("packet evidence entries must be objects")
        lines.append(
            "| {eid} | {rid} | {state} | {source} | {observed} | {expires} | {note} |".format(
                eid=_md_cell(item.get("id", "")),
                rid=_md_cell(item.get("requirement_id", "")),
                state=_md_cell(item.get("state", "")),
                source=_md_cell(item.get("source_ref", "")),
                observed=_md_cell(item.get("observed_on", "")),
                expires=_md_cell(item.get("expires_on") or "—"),
                note=_md_cell(item.get("note", "") or "—"),
            )
        )
    return "\n".join(lines) + "\n"


def export_room_markdown(room: Mapping[str, Any]) -> str:
    """Render each partner packet without ranking candidates."""

    partners = room.get("partners")
    if not isinstance(partners, list) or not partners:
        raise QualificationError("room.partners must be a non-empty list")
    sections = [export_human_review_markdown(packet).rstrip() for packet in partners]
    return "\n\n---\n\n".join(sections) + "\n"


def _read_json(path: str) -> Mapping[str, Any]:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot read input JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise QualificationError("input JSON must be an object")
    return value


def cli_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate source-linked partner qualification evidence")
    parser.add_argument("input", help="JSON input path, or - for stdin")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        doc = _read_json(args.input)
        opportunity = doc.get("opportunity")
        as_of = doc.get("as_of")
        has_partner = "partner" in doc
        has_partners = "partners" in doc
        if has_partner == has_partners:
            raise QualificationError("input must contain exactly one of partner or partners")
        if has_partner:
            output = evaluate_partner(opportunity, doc["partner"], as_of=as_of)
            rendered = (
                json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                if args.format == "json"
                else export_human_review_markdown(output)
            )
        else:
            output = evaluate_room(opportunity, doc["partners"], as_of=as_of)
            rendered = (
                json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                if args.format == "json"
                else export_room_markdown(output)
            )
    except QualificationError as exc:
        parser.error(str(exc))
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
