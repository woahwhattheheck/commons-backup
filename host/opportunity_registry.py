#!/usr/bin/env python3
"""Compile and read the fail-closed Commons opportunity registry.

Composes the public grants ledger, White Box offers, collaboration targets,
and procurement channels with exact repository receipts. Does not submit
applications, accept terms, or claim awards, partnerships, IP, or cash.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from datetime import date, datetime
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = Path("revenue/ip/opportunity_seed.json")
SCHEMA_PATH = Path("revenue/ip/opportunity_registry.schema.json")
REGISTRY_PATH = Path("revenue/ip/opportunity_registry.json")
PACKET_DIR = Path("revenue/ip/packets")
HTML_PATH = Path("opportunity.html")
PROOF_PATH = Path("proof-to-proposal.html")
BASE_SHA = "6a09762980a0597fafc47aff620a4ac633e93c1f"
AS_OF = "2026-08-28T17:15:00Z"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DATE_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TIME_TEXT = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
ID_TEXT = re.compile(r"^[a-z0-9][a-z0-9-]{7,79}$")
DNS_HOST = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))+$"
)
PRIVATE_KEYS = {
    "application_draft",
    "bank_details",
    "collaboration_letter_files",
    "contact_email",
    "contact_phone",
    "entity_identifier",
    "payout_details",
    "research_portal_identity",
    "tax_identifier",
}
LANES = ("GRANT", "PILOT", "LICENSING", "PROCUREMENT", "RESEARCH")
GRANT_CAPS = {
    "nsf-pesose-26-506": [
        "ringdelta-muhlnickel",
        "titan-hands",
        "carrier-infrastructure",
        "reliability-trust",
    ],
    "nsf-sbir-sttr-26-510": [
        "titan-hands",
        "reliability-trust",
        "resource-feature-trackers",
    ],
    "nlnet-restack-ois-2026": [
        "ringdelta-muhlnickel",
        "carrier-infrastructure",
        "evidence-record",
        "agent-swarm",
    ],
}
COLLAB_CAPS = {
    "eleutherai-lm-eval-harness": ["reliability-trust", "evidence-record"],
    "mlcommons-inference": ["reliability-trust", "evidence-record"],
    "hugging-face-hub": ["titan-hands", "carrier-infrastructure"],
    "nvidia-tensorrt-llm": ["titan-hands", "reliability-trust"],
    "ggml-llama-cpp": ["titan-hands", "ringdelta-muhlnickel"],
    "bitsandbytes-foundation": ["reliability-trust", "evidence-record"],
}
OFFER_LANE = {
    "whitebox-archive-license": "LICENSING",
    "whitebox-sponsored-benchmark": "PILOT",
    "whitebox-joint-paper-reproduction": "RESEARCH",
    "whitebox-private-evaluation": "PILOT",
    "whitebox-advisory-hour": "PILOT",
}
PROCUREMENT_CAPS = ["carrier-infrastructure", "resource-feature-trackers", "evidence-record"]
COMMON_NONCLAIMS = [
    "Program language is not an applicant eligibility finding.",
    "No application, award, partnership, IP assignment, or cash is recorded.",
    "A packet is not a submission.",
]
VOLATILE_CAPABILITY_PROJECTIONS = frozenset({
    "features.html",
    "feature-tracker.html",
    "feature-tracker.json",
})


class RegistryError(ValueError):
    """The registry does not match its public evidence contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def _exact_keys(value, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), "%s must be an object" % at)
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, "%s missing keys %r" % (at, missing))
    _require(not extra, "%s has extra keys %r" % (at, extra))


def _walk_private_keys(value, at: str = "$") -> None:
    if isinstance(value, dict):
        found = sorted(PRIVATE_KEYS.intersection(value))
        _require(not found, "%s publishes private keys %r" % (at, found))
        for key, child in value.items():
            _walk_private_keys(child, "%s.%s" % (at, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_private_keys(child, "%s[%d]" % (at, index))


def _reject_duplicate_pairs(pairs):
    parsed = {}
    for key, value in pairs:
        _require(key not in parsed, "duplicate JSON key %r" % key)
        parsed[key] = value
    return parsed


def _reject_nonfinite(value: str):
    raise RegistryError("non-finite JSON constant %s" % value)


def _finite_float(value: str) -> float:
    # parse_constant does not see JSON numbers whose float conversion overflows.
    number = float(value)
    _require(math.isfinite(number), "non-finite JSON number %s" % value)
    return number


def _parse_json(raw: str, at: str):
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_finite_float,
        )
    except json.JSONDecodeError as exc:
        raise RegistryError("%s is malformed JSON" % at) from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_sha256(value) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))


def _https(value, at: str) -> str:
    _require(isinstance(value, str), "%s must be text" % at)
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and bool(parsed.netloc), "%s must be HTTPS" % at)
    _require(parsed.username is None and parsed.password is None, "%s embeds private material" % at)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RegistryError("%s has an invalid port" % at) from exc
    _require(port is None, "%s may not use a port" % at)
    _require(bool(parsed.hostname) and bool(DNS_HOST.fullmatch(parsed.hostname)), "%s has an invalid hostname" % at)
    _require(not any(character.isspace() for character in value), "%s contains whitespace" % at)
    return value


def _timestamp(value, at: str) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), "%s must be a UTC timestamp" % at)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RegistryError("%s is malformed" % at) from exc
    return parsed


def _date(value, at: str) -> date:
    _require(isinstance(value, str) and bool(DATE_TEXT.fullmatch(value)), "%s is malformed" % at)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RegistryError("%s is malformed" % at) from exc


def _nonempty_text(value, at: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), "%s must be nonempty text" % at)
    return value


def freshness(deadline, application_state: str, as_of: datetime) -> tuple[str, str]:
    if application_state == "NOT_APPLICABLE":
        return "NOT_APPLICABLE", "Not an application window."
    if application_state == "ROLLING" and deadline == "UNKNOWN":
        return "ROLLING", "Official page publishes no closing date; applications are described as accepted through the portal."
    if deadline == "UNKNOWN":
        return "UNKNOWN", "No independently verified deadline was copied into this row."
    _require(isinstance(deadline, dict), "deadline must be an object or UNKNOWN")
    due = _date(deadline["date"], "deadline.date")
    as_of_date = as_of.date()
    delta = (due - as_of_date).days
    if delta <= 0:
        return "PAST", "Deadline date %s is not after as_of %s. This is not a submission." % (due.isoformat(), as_of_date.isoformat())
    if delta <= 14:
        return "URGENT", "Deadline date %s is %d day(s) after as_of %s." % (due.isoformat(), delta, as_of_date.isoformat())
    if delta <= 45:
        return "SOON", "Deadline date %s is %d day(s) after as_of %s." % (due.isoformat(), delta, as_of_date.isoformat())
    return "SCHEDULED", "Deadline date %s is %d day(s) after as_of %s." % (due.isoformat(), delta, as_of_date.isoformat())


def _row(
    *,
    oid: str,
    lane: str,
    name: str,
    funder: str,
    official_urls: list[str],
    composed_from: list[dict],
    checked_at: str,
    application_state: str,
    application_state_basis: str,
    opens_date,
    deadline,
    as_of: datetime,
    program_eligibility_text: str,
    program_eligibility_evidence_state: str,
    fit_note: str,
    capability_ids: list[str],
    owner_action: str,
    required_artifacts: list[str],
    stated_funding_text: str,
    stated_funding_evidence_state: str,
    probability_state: str,
    submission_status: str,
    private_blockers: list[str],
    fit_state: str = "ANALYSIS_ONLY",
    extra_nonclaims: list[str] | None = None,
) -> dict:
    fresh, basis = freshness(deadline, application_state, as_of)
    urls = list(official_urls)
    nonclaims = list(COMMON_NONCLAIMS)
    if extra_nonclaims:
        for item in extra_nonclaims:
            if item not in nonclaims:
                nonclaims.append(item)
    return {
        "id": oid,
        "lane": lane,
        "name": name,
        "funder_or_counterparty": funder,
        "official_urls": urls,
        "evidence_urls": list(urls),
        "composed_from": composed_from,
        "checked_at": checked_at,
        "application_state": application_state,
        "application_state_basis": application_state_basis,
        "opens_date": opens_date,
        "deadline": deadline,
        "deadline_freshness": fresh,
        "deadline_freshness_basis": basis,
        "program_eligibility_text": program_eligibility_text,
        "program_eligibility_evidence_state": program_eligibility_evidence_state,
        "applicant_eligibility_state": "UNKNOWN",
        "fit": {
            "state": fit_state,
            "note": fit_note,
            "capability_ids": list(capability_ids),
        },
        "owner_action": owner_action,
        "owner": "COMMONS_ANY_PEER",
        "required_artifacts": list(required_artifacts),
        "stated_funding_text": stated_funding_text,
        "stated_funding_evidence_state": stated_funding_evidence_state,
        "expected_value_usd": "UNKNOWN",
        "expected_value_state": "UNKNOWN",
        "probability_state": probability_state,
        "packet_id": "packet-%s" % oid[:71],
        "submission_status": submission_status,
        "award_status": "NOT_AWARDED",
        "cash_received_usd": 0,
        "contacted": False,
        "partnership_claimed": False,
        "private_blockers": list(private_blockers),
        "nonclaims": nonclaims,
    }


def _receipts(root: Path, paths: list[str]) -> list[dict]:
    volatile = sorted(VOLATILE_CAPABILITY_PROJECTIONS.intersection(paths))
    _require(
        not volatile,
        "volatile generated capability projections are not evidence: %r" % volatile,
    )
    out = []
    for rel in paths:
        path = root / rel
        _require(path.is_file(), "missing receipt %s" % rel)
        data = path.read_bytes()
        out.append({"path": rel, "sha256": sha256_bytes(data), "bytes": len(data)})
    return out


def _source(root: Path, rel: str) -> dict:
    path = root / rel
    _require(path.is_file(), "missing composed source %s" % rel)
    return {"path": rel, "sha256": sha256_file(path)}


def compile_registry(root: Path) -> dict:
    seed = _parse_json((root / SEED_PATH).read_text(encoding="utf-8"), "seed")
    _require(seed.get("kind") == "OPPORTUNITY_SEED", "seed kind mismatch")
    _require(seed.get("generated_from_main") == BASE_SHA, "seed main drift")
    _require(seed.get("as_of") == AS_OF, "seed as_of drift")
    as_of = _timestamp(seed["as_of"], "as_of")
    capabilities = []
    for cap in seed["capabilities"]:
        capabilities.append({
            "id": cap["id"],
            "name": cap["name"],
            "status": cap["status"],
            "receipts": _receipts(root, cap["receipts"]),
        })
    cap_ids = {row["id"] for row in capabilities}
    compose_meta = []
    for item in seed["compose"]:
        src = _source(root, item["path"])
        compose_meta.append({
            "id": item["id"],
            "path": item["path"],
            "role": item["role"],
            "sha256": src["sha256"],
        })
    grants = _parse_json((root / "revenue/ip/grants_ledger.json").read_text(encoding="utf-8"), "grants")
    collab = _parse_json((root / "revenue/ip/collaboration_targets.json").read_text(encoding="utf-8"), "collab")
    offers = _parse_json((root / "revenue/ip/whitebox_collaboration_offers.json").read_text(encoding="utf-8"), "offers")
    channels = _parse_json((root / "revenue/distribution/channels.json").read_text(encoding="utf-8"), "channels")
    grant_src = _source(root, "revenue/ip/grants_ledger.json")
    collab_src = _source(root, "revenue/ip/collaboration_targets.json")
    offer_src = _source(root, "revenue/ip/whitebox_collaboration_offers.json")
    channel_src = _source(root, "revenue/distribution/channels.json")
    seed_src = _source(root, SEED_PATH.as_posix())
    titan_hour_src = _source(root, "titan-hour.html")

    rows = []
    for program in grants["programs"]:
        oid = program["id"]
        caps = GRANT_CAPS[oid]
        _require(set(caps) <= cap_ids, "unknown grant capability")
        rows.append(_row(
            oid=oid,
            lane="GRANT",
            name=program["program"],
            funder=program["funder"],
            official_urls=program["official_urls"],
            composed_from=[grant_src],
            checked_at=program["checked_at"],
            application_state=program["application_state"],
            application_state_basis=program["application_state_basis"],
            opens_date=program["opens_date"],
            deadline=program["deadline"],
            as_of=as_of,
            program_eligibility_text=program["program_eligibility_text"],
            program_eligibility_evidence_state=program["program_eligibility_evidence_state"],
            fit_note=program["fit_note"],
            capability_ids=caps,
            owner_action=program["public_next_action"],
            required_artifacts=program["deliverables"] + [
                "Compare already-public Commons receipts listed on the packet. Do not file."
            ],
            stated_funding_text=program["funding_text"],
            stated_funding_evidence_state=program["funding_evidence_state"],
            probability_state="PACKET_READY_NOT_SUBMITTED",
            submission_status="NOT_SUBMITTED",
            private_blockers=program["private_blockers"],
            extra_nonclaims=program["nonclaims"],
        ))

    for program in seed["seed_programs"]:
        caps = program["capability_ids"]
        _require(set(caps) <= cap_ids, "unknown seed capability")
        if program["id"] == "commons-public-license-unknown":
            probability = "BLOCKED_LICENSE_UNKNOWN"
            submission = "NOT_APPLICABLE"
            fit_state = "BLOCKED"
        elif program["application_state"] in {"OPEN", "UPCOMING", "ROLLING"}:
            probability = "PACKET_READY_NOT_SUBMITTED"
            submission = "NOT_SUBMITTED"
            fit_state = "ANALYSIS_ONLY"
        else:
            probability = "NONE_READY"
            submission = "NOT_SUBMITTED"
            fit_state = "ANALYSIS_ONLY"
        rows.append(_row(
            oid=program["id"],
            lane=program["lane"],
            name=program["name"],
            funder=program["funder_or_counterparty"],
            official_urls=program["official_urls"],
            composed_from=[seed_src],
            checked_at=seed["checked_at"],
            application_state=program["application_state"],
            application_state_basis=program["application_state_basis"],
            opens_date=program["opens_date"],
            deadline=program["deadline"],
            as_of=as_of,
            program_eligibility_text=program["program_eligibility_text"],
            program_eligibility_evidence_state=program["program_eligibility_evidence_state"],
            fit_note=program["fit_note"],
            capability_ids=caps,
            owner_action=program["public_next_action"],
            required_artifacts=program["deliverables"],
            stated_funding_text=program["funding_text"],
            stated_funding_evidence_state=program["funding_evidence_state"],
            probability_state=probability,
            submission_status=submission,
            private_blockers=program["private_blockers"],
            fit_state=fit_state,
        ))

    for target in collab["targets"]:
        oid = "research-%s" % target["id"]
        caps = COLLAB_CAPS[target["id"]]
        rows.append(_row(
            oid=oid,
            lane="RESEARCH",
            name=target["entity"],
            funder=target["entity"],
            official_urls=[target["source"]["immutable_url"]],
            composed_from=[collab_src],
            checked_at=collab["generated_at"],
            application_state="NOT_APPLICABLE",
            application_state_basis="Collaboration-target research ledger. Status %s. Not a grant call." % target["status"],
            opens_date="UNKNOWN",
            deadline="UNKNOWN",
            as_of=as_of,
            program_eligibility_text=target["evidence_limit"],
            program_eligibility_evidence_state="VERIFIED",
            fit_note="ANALYSIS: %s This is a hypothesis from public repository text, not contact or partnership." % target["collaboration_hypothesis"],
            capability_ids=caps,
            owner_action=target["next_action"],
            required_artifacts=[
                "Public no-private-data packet against already-cleared inputs.",
                "Do not contact the target from this registry.",
            ],
            stated_funding_text="UNKNOWN: collaboration targets record no funding amount.",
            stated_funding_evidence_state="UNKNOWN",
            probability_state="RESEARCHED_NOT_CONTACTED",
            submission_status="NOT_APPLICABLE",
            private_blockers=[
                "Owner choice to contact",
                "Cleared customer-owned or public inputs",
            ],
        ))

    offer_map = {row["id"]: row for row in offers["offers"]}
    for entry in offers.get("entry_routes") or []:
        offer_map[entry["id"]] = {
            "id": entry["id"],
            "name": "White Box advisory hour",
            "state": entry["status"],
            "price": entry["price"],
            "deliverable": "One bounded advisory hour on the existing White Box-hour SKU.",
            "blocker": "",
            "customer_supplies": "A public, non-confidential objective.",
        }
    for oid, lane in OFFER_LANE.items():
        offer = offer_map[oid]
        price = offer.get("price") or {}
        if price.get("known") is True and price.get("amount_usd") is not None:
            funding = "Live offer states USD %s on a %s basis. This is a price, not cash received." % (
                price["amount_usd"],
                price.get("basis", "UNKNOWN"),
            )
            funding_state = "VERIFIED"
        else:
            funding = "UNKNOWN: price is not established on the composed offer row."
            funding_state = "UNKNOWN"
        blocked = bool(offer.get("blocker"))
        live = offer.get("state") in {"LIVE_CHECKOUT", "AVAILABLE_CUSTOMER_OWNED_ASSET", "SCOPING_AVAILABLE"}
        if blocked:
            probability = "BLOCKED_EVIDENCE"
            fit_state = "BLOCKED"
            submission = "NOT_APPLICABLE"
            app_state = "NOT_APPLICABLE"
        elif live:
            probability = "LIVE_OFFER_NOT_AN_APPLICATION"
            fit_state = "LIVE_OFFER"
            submission = "NOT_APPLICABLE"
            app_state = "NOT_APPLICABLE"
        else:
            probability = "NONE_READY"
            fit_state = "ANALYSIS_ONLY"
            submission = "NOT_APPLICABLE"
            app_state = "NOT_APPLICABLE"
        rows.append(_row(
            oid=oid,
            lane=lane,
            name=offer["name"],
            funder="Commons public offer",
            official_urls=["https://woahwhattheheck.github.io/commons/commercial.html"],
            composed_from=[offer_src],
            checked_at=offers["generated_at"],
            application_state=app_state,
            application_state_basis="Composed from whitebox_collaboration_offers.json state %s. This is an offer Commons publishes, not a funder application." % offer.get("state"),
            opens_date="UNKNOWN",
            deadline="UNKNOWN",
            as_of=as_of,
            program_eligibility_text=offer.get("deliverable") or "",
            program_eligibility_evidence_state="VERIFIED" if offer.get("deliverable") else "UNKNOWN",
            fit_note="ANALYSIS: Existing public offer row %s. Buyer interest, agreement, delivery, and cash remain unclaimed." % oid,
            capability_ids=["titan-hands", "reliability-trust", "evidence-record"],
            owner_action="Keep the public offer accurate. Do not invent buyers or cash. %s" % (offer.get("blocker") or "Fulfill only against verified checkout and a named customer-owned asset."),
            required_artifacts=[
                offer.get("customer_supplies") or "Customer-owned or independently cleared inputs.",
                "Public-safe receipt if any hour or pilot actually runs.",
            ],
            stated_funding_text=funding,
            stated_funding_evidence_state=funding_state,
            probability_state=probability,
            submission_status=submission,
            private_blockers=[
                offer.get("blocker") or "Owner fulfillment capacity",
                "No fabricated demand",
            ],
            fit_state=fit_state,
        ))

    rows.append(_row(
        oid="titan-hands-activation-hour",
        lane="PILOT",
        name="TITAN Hands Activation Hour",
        funder="Commons public offer",
        official_urls=["https://woahwhattheheck.github.io/commons/titan-hour.html"],
        composed_from=[titan_hour_src],
        checked_at=AS_OF,
        application_state="NOT_APPLICABLE",
        application_state_basis="Public service hour on the existing White Box-hour SKU. Not a funder application.",
        opens_date="UNKNOWN",
        deadline="UNKNOWN",
        as_of=as_of,
        program_eligibility_text="$250 buys one dated White Box / dests hour using TITAN Hands when the agreed objective calls for it. Payment never grants standing tool, device, wireless, account, or mutation authority.",
        program_eligibility_evidence_state="VERIFIED",
        fit_note="ANALYSIS: titan-hour.html is a live public service door composed here as a pilot offer, not a grant application.",
        capability_ids=["titan-hands", "reliability-trust"],
        owner_action="Keep the hour contract accurate. Do not claim a paid session without a dated public-safe receipt.",
        required_artifacts=[
            "Exact intake: one objective, one target surface, proof that will count, stop condition, scheduling windows.",
            "Dated public-safe land/session receipt if an hour actually runs.",
        ],
        stated_funding_text="Live offer states USD 250 per hour. This is a price, not cash received.",
        stated_funding_evidence_state="VERIFIED",
        probability_state="LIVE_OFFER_NOT_AN_APPLICATION",
        submission_status="NOT_APPLICABLE",
        private_blockers=["Owner fulfillment capacity", "No fabricated demand"],
        fit_state="LIVE_OFFER",
    ))

    for channel in channels["channels"]:
        if channel.get("family") != "procurement":
            continue
        rows.append(_row(
            oid="procurement-%s" % channel["id"],
            lane="PROCUREMENT",
            name=channel["name"],
            funder=channel["name"],
            official_urls=[channel["official_url"]],
            composed_from=[channel_src],
            checked_at=channels["snapshot_as_of"],
            application_state="NOT_APPLICABLE",
            application_state_basis="Distribution layer account_status=%s submit_allowed=%s honest_live=%s. This layer never submits." % (
                channel.get("account_status"),
                channel.get("submit_allowed"),
                channel.get("honest_live"),
            ),
            opens_date="UNKNOWN",
            deadline="UNKNOWN",
            as_of=as_of,
            program_eligibility_text=channel.get("notes") or channel.get("guidance") or "",
            program_eligibility_evidence_state="VERIFIED",
            fit_note="ANALYSIS: Procurement channel %s is composed from the distribution layer. Absence of CAGE, UEI, SAM, or GSA evidence is recorded, not repaired." % channel["id"],
            capability_ids=PROCUREMENT_CAPS,
            owner_action="Generate a truthful pack only. Do not register, submit, or invent a federal-ready status.",
            required_artifacts=[
                "Named public RFP or portal record if one is later cited.",
                "Existing distribution package from host/distribution.py. Do not submit it.",
            ],
            stated_funding_text="UNKNOWN: no named solicitation amount is on current main.",
            stated_funding_evidence_state="UNKNOWN",
            probability_state="BLOCKED_REGISTRATION",
            submission_status="NOT_SUBMITTED",
            private_blockers=[
                "CAGE / UEI / SAM / GSA evidence",
                "Owner legal identity",
                "Authorized portal account",
            ],
            fit_state="BLOCKED",
        ))

    ids = [row["id"] for row in rows]
    _require(len(ids) == len(set(ids)), "duplicate opportunity ids")
    lanes = {lane: 0 for lane in LANES}
    for row in rows:
        lanes[row["lane"]] += 1
        _require(row["cash_received_usd"] == 0, "cash fabrication")
        _require(row["award_status"] == "NOT_AWARDED", "award fabrication")
        _require(row["applicant_eligibility_state"] == "UNKNOWN", "eligibility adjudication")
        _require(row["contacted"] is False, "contact fabrication")
        _require(row["partnership_claimed"] is False, "partnership fabrication")
        _require(row["expected_value_usd"] == "UNKNOWN", "expected-value fabrication")
    none_ready = sum(1 for row in rows if row["probability_state"] in {"NONE_READY", "PACKET_READY_NOT_SUBMITTED", "BLOCKED_LICENSE_UNKNOWN", "BLOCKED_EVIDENCE", "BLOCKED_REGISTRATION"})
    registry = {
        "schema_version": "commons-opportunity-registry/v1",
        "kind": "OPPORTUNITY_REGISTRY",
        "generated_at": AS_OF,
        "generated_from_main": BASE_SHA,
        "as_of": AS_OF,
        "scope": seed["scope"],
        "nonclaims": [
            "This registry is research and packaging, not filing.",
            "Applicant eligibility is UNKNOWN for every row.",
            "Zero applications submitted, zero awards, zero partnerships, zero cash.",
            "Expected value stays UNKNOWN; official funding text is not a forecast.",
            "Live Commons offers are prices, not receipts of payment.",
            "Do not submit, accept terms, or mint legal identity from this door.",
        ],
        "legal_scope": {
            "applicant_eligibility_adjudicated": False,
            "submission_readiness_claimed": False,
            "application_submitted": False,
            "award_claimed": False,
            "partnership_claimed": False,
            "ip_rights_claimed": False,
            "funding_success_claimed": False,
            "cash_received_claimed": False,
        },
        "omitted_private_fields": sorted(PRIVATE_KEYS),
        "compose": compose_meta,
        "capabilities": capabilities,
        "counts": {
            "opportunities": len(rows),
            "grants": lanes["GRANT"],
            "pilots": lanes["PILOT"],
            "licensing": lanes["LICENSING"],
            "procurement": lanes["PROCUREMENT"],
            "research": lanes["RESEARCH"],
            "submitted": 0,
            "awarded": 0,
            "cash_received_usd": 0,
            "none_ready": none_ready,
        },
        "opportunities": rows,
    }
    return registry


def validate(root: Path, registry: dict, schema: dict) -> dict:
    del root
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema draft mismatch")
    _require(schema.get("$id", "").endswith("/revenue/ip/opportunity_registry.schema.json"), "schema id mismatch")
    _require(schema.get("additionalProperties") is False, "schema is open")
    _walk_private_keys(registry)
    _require(registry.get("schema_version") == "commons-opportunity-registry/v1", "schema_version mismatch")
    _require(registry.get("kind") == "OPPORTUNITY_REGISTRY", "kind mismatch")
    _require(registry.get("generated_from_main") == BASE_SHA, "generated_from_main drift")
    _require(registry.get("as_of") == AS_OF, "as_of drift")
    _timestamp(registry["generated_at"], "generated_at")
    legal = registry["legal_scope"]
    _require(all(value is False for value in legal.values()), "legal_scope must be exact false")
    _require(set(registry["omitted_private_fields"]) == PRIVATE_KEYS, "private field omission incomplete")
    counts = registry["counts"]
    _require(counts["submitted"] == 0, "submitted fabrication")
    _require(counts["awarded"] == 0, "award fabrication")
    _require(counts["cash_received_usd"] == 0, "cash fabrication")
    opportunities = registry["opportunities"]
    _require(isinstance(opportunities, list) and opportunities, "opportunities empty")
    ids = []
    for index, row in enumerate(opportunities):
        at = "opportunities[%d]" % index
        _require(bool(ID_TEXT.fullmatch(row["id"])), "%s.id invalid" % at)
        _require(row["lane"] in LANES, "%s.lane invalid" % at)
        _require(row["applicant_eligibility_state"] == "UNKNOWN", "%s eligibility adjudicated" % at)
        _require(row["expected_value_usd"] == "UNKNOWN", "%s expected value fabricated" % at)
        _require(row["cash_received_usd"] == 0 and not isinstance(row["cash_received_usd"], bool), "%s cash fabricated" % at)
        _require(row["award_status"] == "NOT_AWARDED", "%s award fabricated" % at)
        _require(row["contacted"] is False, "%s contacted fabricated" % at)
        _require(row["partnership_claimed"] is False, "%s partnership fabricated" % at)
        _require(row["fit"]["note"].startswith("ANALYSIS:"), "%s fit note" % at)
        _require(row["owner"].startswith("COMMONS_ANY_"), "%s exclusive owner" % at)
        for url in row["official_urls"] + row["evidence_urls"]:
            _https(url, "%s.url" % at)
        ids.append(row["id"])
    _require(len(ids) == len(set(ids)), "duplicate ids")
    _require(counts["opportunities"] == len(opportunities), "count drift")
    lane_counts = {lane: 0 for lane in LANES}
    for row in opportunities:
        lane_counts[row["lane"]] += 1
    count_key = {
        "GRANT": "grants",
        "PILOT": "pilots",
        "LICENSING": "licensing",
        "PROCUREMENT": "procurement",
        "RESEARCH": "research",
    }
    for lane in LANES:
        _require(counts[count_key[lane]] == lane_counts[lane], "%s count drift" % lane)
    return {
        "status": "VALID",
        "opportunities": len(opportunities),
        "lanes": dict(sorted(lane_counts.items())),
        "submitted": 0,
        "awarded": 0,
        "cash_received_usd": 0,
        "next": "NONE_READY",
        "reason": "APPLICANT_ELIGIBILITY_UNKNOWN",
    }


def load(root: Path = ROOT) -> tuple[dict, dict]:
    registry = _parse_json((root / REGISTRY_PATH).read_text(encoding="utf-8"), "registry")
    schema = _parse_json((root / SCHEMA_PATH).read_text(encoding="utf-8"), "schema")
    return registry, schema


def render_packet(row: dict, capabilities: list[dict]) -> str:
    cap_map = {item["id"]: item for item in capabilities}
    lines = [
        "# Proof-to-proposal packet: %s" % row["name"],
        "",
        "Packet id: `%s`" % row["packet_id"],
        "Opportunity id: `%s`" % row["id"],
        "Lane: `%s`" % row["lane"],
        "",
        "This packet is generated from exact repository receipts. It is **not** an application, pitch email, partnership, award, or invoice.",
        "",
        "## Nonclaims",
        "",
    ]
    for item in row["nonclaims"]:
        lines.append("- %s" % item)
    lines.extend(["", "## Official source", ""])
    for url in row["official_urls"]:
        lines.append("- %s" % url)
    lines.extend([
        "",
        "## Deadline freshness",
        "",
        "- application_state: `%s`" % row["application_state"],
        "- deadline: `%s`" % json.dumps(row["deadline"], sort_keys=True),
        "- freshness: `%s`" % row["deadline_freshness"],
        "- basis: %s" % row["deadline_freshness_basis"],
        "",
        "## Fit (analysis only)",
        "",
        row["fit"]["note"],
        "",
        "## Capability receipts",
        "",
    ])
    for cap_id in row["fit"]["capability_ids"]:
        cap = cap_map[cap_id]
        lines.append("### %s (`%s`, `%s`)" % (cap["name"], cap["id"], cap["status"]))
        lines.append("")
        for rec in cap["receipts"]:
            lines.append("- `%s` sha256 `%s` (%d bytes)" % (rec["path"], rec["sha256"], rec["bytes"]))
        lines.append("")
    lines.extend([
        "## Stated funding (not expected value)",
        "",
        row["stated_funding_text"],
        "",
        "expected_value_usd: UNKNOWN",
        "",
        "## Required artifacts",
        "",
    ])
    for item in row["required_artifacts"]:
        lines.append("- %s" % item)
    lines.extend([
        "",
        "## Owner action",
        "",
        row["owner_action"],
        "",
        "## Private blockers (not published as facts)",
        "",
    ])
    for item in row["private_blockers"]:
        lines.append("- %s" % item)
    lines.extend([
        "",
        "## Probability state",
        "",
        "`%s` — not a numeric forecast." % row["probability_state"],
        "",
        "submission_status: `%s`. award_status: `NOT_AWARDED`. cash_received_usd: `0`. contacted: `false`. partnership_claimed: `false`." % row["submission_status"],
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def write_packets(root: Path, registry: dict) -> list[str]:
    directory = root / PACKET_DIR
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for row in registry["opportunities"]:
        rel = PACKET_DIR / ("%s.md" % row["packet_id"])
        text = render_packet(row, registry["capabilities"])
        (root / rel).write_text(text, encoding="utf-8")
        written.append(str(rel).replace("\\", "/"))
    index = ["# Proof-to-proposal packets", "", "Generated from the opportunity registry. Packets are not filings.", ""]
    for row in registry["opportunities"]:
        index.append("- [%s](./%s.md) — `%s` `%s` `%s`" % (
            row["name"],
            row["packet_id"],
            row["lane"],
            row["deadline_freshness"],
            row["probability_state"],
        ))
    index.append("")
    (directory / "README.md").write_text("\n".join(index).rstrip() + "\n", encoding="utf-8")
    written.append("revenue/ip/packets/README.md")
    return written


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def render_opportunity_html(registry: dict) -> str:
    counts = registry["counts"]
    cards = []
    for row in registry["opportunities"]:
        deadline = row["deadline"]["date"] if isinstance(row["deadline"], dict) else "UNKNOWN"
        cards.append(
            """<article class="panel opp" data-lane="{lane}" data-fresh="{fresh}" id="{oid}">
<h3>{name}</h3>
<p class="note">{funder} · <code>{lane}</code> · <span class="state">{fresh}</span> · <span class="state">{prob}</span></p>
<dl class="struct">
<dt>Fit</dt><dd>{fit}</dd>
<dt>Eligibility</dt><dd>applicant <code>UNKNOWN</code>. program evidence <code>{pelig}</code>.</dd>
<dt>Deadline</dt><dd>{deadline} — {basis}</dd>
<dt>Source</dt><dd>{urls}</dd>
<dt>Owner action</dt><dd>{action}</dd>
<dt>Required artifacts</dt><dd>{arts}</dd>
<dt>Stated funding</dt><dd>{fund} Expected value: <code>UNKNOWN</code>.</dd>
<dt>Packet</dt><dd><a href="./revenue/ip/packets/{packet}.md"><code>{packet}</code></a></dd>
</dl>
</article>""".format(
                lane=_esc(row["lane"]),
                fresh=_esc(row["deadline_freshness"]),
                oid=_esc(row["id"]),
                name=_esc(row["name"]),
                funder=_esc(row["funder_or_counterparty"]),
                prob=_esc(row["probability_state"]),
                fit=_esc(row["fit"]["note"]),
                pelig=_esc(row["program_eligibility_evidence_state"]),
                deadline=_esc(deadline),
                basis=_esc(row["deadline_freshness_basis"]),
                urls=" ".join('<a href="%s">%s</a>' % (_esc(url), _esc(url)) for url in row["official_urls"]),
                action=_esc(row["owner_action"]),
                arts="<br>".join(_esc(item) for item in row["required_artifacts"]),
                fund=_esc(row["stated_funding_text"]),
                packet=_esc(row["packet_id"]),
            )
        )
    caps = []
    for cap in registry["capabilities"]:
        recs = "<br>".join("%s · <code>%s</code>" % (_esc(item["path"]), _esc(item["sha256"][:16])) for item in cap["receipts"])
        caps.append("<tr><th>%s</th><td><code>%s</code></td><td>%s</td><td>%s</td></tr>" % (
            _esc(cap["name"]), _esc(cap["id"]), _esc(cap["status"]), recs
        ))
    body = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow">
<title>Commons opportunity registry — grants, pilots, licensing, procurement, research</title>
<link rel="stylesheet" href="./commons.css?v=20260823f">
<style>
body{max-width:78rem}
.hero h1{font-size:clamp(2.1rem,6vw,4.6rem);line-height:.96;max-width:16ch;margin:.25rem 0 1rem;text-wrap:balance}
.truth{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));gap:.4rem}
.truth span{border:1px solid #33333a;padding:.5rem;text-align:center}
.truth b{display:block;font:700 1.2rem/1.2 ui-monospace,monospace}
.filters{display:flex;flex-wrap:wrap;gap:.4rem;margin:.6rem 0}
.filters button{border:1px solid #55555f;background:#161618;color:inherit;border-radius:999px;padding:.45rem .8rem;min-height:44px}
.filters button[aria-pressed="true"]{border-color:#9aa3ad;background:#1a1c20}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(22rem,100%),1fr));gap:1rem}
.panel{border:1px solid #383840;border-radius:16px;padding:1rem;background:#111114}
.opp,.struct,.struct dd{min-width:0}
.struct dd,.struct a{overflow-wrap:anywhere}
table{font-size:.86rem}
.cta{display:inline-block;margin:.45rem .4rem .45rem 0;padding:.7rem 1.05rem;border:1px solid #62b879;border-radius:8px;background:#f0f0f2;color:#09090b!important;font-weight:800;text-decoration:none}
.cta:hover{filter:brightness(1.06)}
</style>
</head>
<body>
<section id="trust-through-proof" class="law trust-law" aria-label="Trust after proof — operating law"><strong>TRUST AFTER PROOF.</strong> <a href="./trust.html">Read “On Trust.”</a> Proof is cached. Build unless the bytes moved. <strong>Commerce is included:</strong> never invent buyers, replies, payments, applications, awards, or partnerships.</section>
<p class="law">OPEN OPPORTUNITY DOOR. Non-dilutive lane only: grants, pilots, licensing, procurement, research partnerships. No login. No submission from this page. Applicant eligibility is UNKNOWN. Cash is 0.</p>
<p class="nav"><a href="./index.html">Commons</a> · <a href="./current-work.html">current work</a> · <a href="./listing-registry.html">listing registry</a> · <a href="./distribution.html">distribution</a> · <a href="./proof-to-proposal.html">proof-to-proposal</a> · <a href="./commercial.html">commercial</a> · <a href="./ground/PROFITABILITY_BUILD_MAP.md">profitability</a> · <a href="./action.html">Action Pad</a></p>
<header class="hero">
<p class="note">Opportunity registry · <code>host/opportunity_registry.py</code> · as_of __AS_OF__</p>
<h1>Verified public technology. Honest non-dilutive doors. Zero invented money.</h1>
<section id="titanmcp-pad-pointer" class="law" aria-label="titanmcp contest pad">
  <strong>titanmcp pad (contest):</strong> <a href="https://webmcp-pad.vercel.app/">webmcp-pad.vercel.app</a> — <code>titanmcp 1.4.5</code> · 24 tools · Agent Resources · <a href="./titanmcp.html">titanmcp.html</a>. Commons Shared Pad is <a href="./webmcp.html">webmcp.html</a>. Commons <code>/mcp</code> KEEP separate.
</section>

<section id="buy-now-live-checkout" class="law" aria-label="Buy now — live checkout">
<strong>Buy now — live checkout.</strong> Existing live Payment Links. No invented Stripe. A click is intent, not cash.
<p>
<a class="cta" data-checkout href="https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07">Buy one White Box hour $250</a>
</p>
<p class="note">Reuse only. Cite <code>wire-opportunity-claims-convert-shelf-20260917-01</code>. Sources: <a href="./commercial.html">commercial.html</a> / <a href="./diagnostic.html">diagnostic.html</a>. Tip KEEP. #8802 off. No new Payment Links.</p>
</section>

<section id="live-cash" aria-label="Live cash">
  <p><strong>Live cash</strong> — verified product pages only (no invented Stripe links).</p>
  <ul>
    <li><a href="./dealer-service-lead-rescue.html">$199 dealer diagnostic</a></li>
    <li><a href="./referral-intake-completeness.html">$199 referral diagnostic</a></li>
    <li><a href="./repair-booking-preflight.html">$199 repair diagnostic</a></li>
    <li><a href="./plant-downtime-handoff.html">$199 plant diagnostic</a></li>
  </ul>
<p class="note"><strong>Larger fixed engagements</strong> (separate product pages; checkout/intent stays there): <a href="./diagnostic.html">GGUF diagnostic · $12,000 / 10 days</a> · <a href="./commercial.html">White Box pilot · $30,000 / 30 days</a>. Not remints of tip SKUs.</p>
  <p>Full catalog: <a href="./commerce.html">commerce.html</a>. Cite forge tip-shelf / spark autopsy — do not remint.</p>
</section>

<p class="lead">Commons already shipped TITAN Hands, RINGDELTA, carrier roads, evidence records, agent-swarm prep, and trust-cache reliability. This desk maps those receipts onto public grants, live pilot offers, licensing blockers, procurement channels, and research targets. It composes, and does not remint, the listing registry (offer × surface marketplace copies). It does not file, register, or cash anything.</p>
</header>
<section class="panel" aria-labelledby="honest-heading">
<h2 id="honest-heading">Honest counts</h2>
<div class="truth">
<span><b>__N__</b>opportunities</span>
<span><b>__GRANTS__</b>grants</span>
<span><b>__PILOTS__</b>pilots</span>
<span><b>__LICENSING__</b>licensing</span>
<span><b>__PROCUREMENT__</b>procurement</span>
<span><b>__RESEARCH__</b>research</span>
<span><b>0</b>submitted</span>
<span><b>0</b>awarded</span>
<span><b>0</b>cash USD</span>
</div>
<p class="note">Machine: <a href="./revenue/ip/opportunity_registry.json">opportunity_registry.json</a>. Schema: <a href="./revenue/ip/opportunity_registry.schema.json">schema</a>. Packets: <a href="./proof-to-proposal.html">proof-to-proposal</a>. next() is <code>NONE_READY / APPLICANT_ELIGIBILITY_UNKNOWN</code>.</p>
</section>
<section class="panel">
<h2>Shipped capabilities (this main)</h2>
<div style="overflow:auto">
<table>
<thead><tr><th>Capability</th><th>id</th><th>status</th><th>receipts</th></tr></thead>
<tbody>
__CAPS__
</tbody>
</table>
</div>
</section>
<section class="panel">
<h2>Registry</h2>
<p>Filter is cosmetic. Every row is in the HTML. JavaScript off still reads the full ledger.</p>
<div class="filters" id="lane-filters">
<button type="button" data-lane="ALL" aria-pressed="true">All</button>
<button type="button" data-lane="GRANT">Grants</button>
<button type="button" data-lane="PILOT">Pilots</button>
<button type="button" data-lane="LICENSING">Licensing</button>
<button type="button" data-lane="PROCUREMENT">Procurement</button>
<button type="button" data-lane="RESEARCH">Research</button>
</div>
<div class="grid" id="opp-grid">
__CARDS__
</div>
</section>
<p class="note">HTTP is not the computer. Possessing the link is authorization. 337 NO.</p>
<script>
(function(){
  var buttons=document.querySelectorAll("#lane-filters button");
  var cards=document.querySelectorAll(".opp");
  buttons.forEach(function(button){
    button.addEventListener("click", function(){
      var lane=button.getAttribute("data-lane");
      buttons.forEach(function(item){ item.setAttribute("aria-pressed", item===button ? "true" : "false"); });
      cards.forEach(function(card){
        card.hidden = lane!=="ALL" && card.getAttribute("data-lane")!==lane;
      });
    });
  });
})();
</script>
</body>
</html>
"""
    return (
        body.replace("__AS_OF__", _esc(registry["as_of"]))
        .replace("__N__", str(counts["opportunities"]))
        .replace("__GRANTS__", str(counts["grants"]))
        .replace("__PILOTS__", str(counts["pilots"]))
        .replace("__LICENSING__", str(counts["licensing"]))
        .replace("__PROCUREMENT__", str(counts["procurement"]))
        .replace("__RESEARCH__", str(counts["research"]))
        .replace("__CAPS__", "\n".join(caps))
        .replace("__CARDS__", "\n".join(cards))
    )


def render_proof_html(registry: dict) -> str:
    items = []
    for row in registry["opportunities"]:
        items.append(
            "<li id=\"{oid}\"><a href=\"./revenue/ip/packets/{packet}.md\"><strong>{name}</strong></a> — <code>{lane}</code> · freshness <code>{fresh}</code> · probability <code>{prob}</code><br>{action}</li>".format(
                oid=_esc(row["id"]),
                packet=_esc(row["packet_id"]),
                name=_esc(row["name"]),
                lane=_esc(row["lane"]),
                fresh=_esc(row["deadline_freshness"]),
                prob=_esc(row["probability_state"]),
                action=_esc(row["owner_action"]),
            )
        )
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow">
<title>Proof-to-proposal — reusable packets from Commons receipts</title>
<link rel="stylesheet" href="./commons.css?v=20260823f">
<style>
.cta{{display:inline-block;margin:.45rem .4rem .45rem 0;padding:.7rem 1.05rem;border:1px solid #62b879;border-radius:8px;background:#f0f0f2;color:#09090b!important;font-weight:800;text-decoration:none}}
.cta:hover{{filter:brightness(1.06)}}
</style>
</head>
<body>
<section id="trust-through-proof" class="law trust-law"><strong>TRUST AFTER PROOF.</strong> Packets cite exact bytes. They are not filings.</section>
<p class="law">OPEN PACKET DOOR. Reuse receipts. Do not submit from this page. Do not paste private identity, bank, tax, or portal credentials.</p>
<p class="nav"><a href="./index.html">Commons</a> · <a href="./opportunity.html">opportunity registry</a> · <a href="./listing-registry.html">listing registry</a> · <a href="./current-work.html">current work</a> · <a href="./distribution.html">distribution</a> · <a href="./commercial.html">commercial</a> · <a href="./ground/PROFITABILITY_BUILD_MAP.md">profitability</a></p>
<h1>Proof to proposal</h1>
<section id="titanmcp-pad-pointer" class="law" aria-label="titanmcp contest pad">
  <strong>titanmcp pad (contest):</strong> <a href="https://webmcp-pad.vercel.app/">webmcp-pad.vercel.app</a> — <code>titanmcp 1.4.5</code> · 24 tools · Agent Resources · <a href="./titanmcp.html">titanmcp.html</a>. Commons Shared Pad is <a href="./webmcp.html">webmcp.html</a>. Commons <code>/mcp</code> KEEP separate.
</section>
<section id="buy-now-live-checkout" class="law" aria-label="Buy now — live checkout">
<strong>Buy now — live checkout.</strong> Existing live Payment Links. No invented Stripe. A click is intent, not cash.
<p>

<a class="cta" data-checkout href="https://buy.stripe.com/8x27sK2Kp3UZ9uF2SC43S07">Buy one White Box hour $250</a>
</p>
<p class="note">Reuse only. Cite <code>sledge-prooftoproposal-theworld-convert-shelf-20260917-01</code>. Sources: <a href="./commercial.html">commercial.html</a> / <a href="./diagnostic.html">diagnostic.html</a>. Tip KEEP. #8802 off. No new Payment Links.</p>
</section>

<p>Each packet is generated by <code>python3 host/opportunity_registry.py compile</code> from hashed receipts already on this main. A packet can be copied into a later owner-directed application. Copying is not filing.</p>
<p>Index: <a href="./revenue/ip/packets/README.md">revenue/ip/packets/README.md</a>.</p>
<ul>
{items}
</ul>
<p class="note">Applicant eligibility UNKNOWN. Submitted 0. Awarded 0. Cash 0.</p>

<section id="live-cash">
  <h2>Live cash</h2>
  <p>Verified product pages only — no invented Stripe links.</p>
  <ul>
    <li><a href="dealer-service-lead-rescue.html">$199 dealer diagnostic</a></li>
    <li><a href="referral-intake-completeness.html">$199 referral diagnostic</a></li>
    <li><a href="repair-booking-preflight.html">$199 repair diagnostic</a></li>
    <li><a href="plant-downtime-handoff.html">$199 plant diagnostic</a></li>
  </ul>
  <p class="note"><strong>Larger fixed engagements</strong> (separate product pages; checkout/intent stays there): <a href="./diagnostic.html">GGUF diagnostic · $12,000 / 10 days</a> · <a href="./commercial.html">White Box pilot · $30,000 / 30 days</a>. Not remints of tip SKUs.</p>
  <p>Shelf: <a href="tools-cash.html">tools-cash.html</a>. Catalog: <a href="commerce.html">commerce.html</a>. Cite spy-html-money-doors-live-cash-20260905-02 — do not remint.</p>
</section>

</body>
</html>
""".format(items="\n".join(items))


def write_surfaces(root: Path, registry: dict) -> None:
    # KEEP tip Larger fixed on opportunity.html + proof-to-proposal.html remints
    # (newbot-01/#14936 + newbot-04/#14947 additive shelves; template lacked them).
    text = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
    (root / REGISTRY_PATH).write_text(text, encoding="utf-8")
    write_packets(root, registry)
    (root / HTML_PATH).write_text(render_opportunity_html(registry), encoding="utf-8")
    (root / PROOF_PATH).write_text(render_proof_html(registry), encoding="utf-8")


def _due(registry: dict) -> dict:
    rows = []
    for row in registry["opportunities"]:
        rows.append({
            "id": row["id"],
            "lane": row["lane"],
            "application_state": row["application_state"],
            "deadline": row["deadline"],
            "deadline_freshness": row["deadline_freshness"],
            "applicant_eligibility_state": row["applicant_eligibility_state"],
            "probability_state": row["probability_state"],
            "submission_status": row["submission_status"],
        })
    rows.sort(key=lambda item: item["deadline"]["date"] if isinstance(item["deadline"], dict) else "9999-12-31")
    return {"status": "VALID", "due": rows}


def _next(registry: dict) -> dict:
    unknown = [row["id"] for row in registry["opportunities"] if row["applicant_eligibility_state"] == "UNKNOWN"]
    return {
        "status": "NONE_READY",
        "reason": "APPLICANT_ELIGIBILITY_UNKNOWN",
        "opportunity_ids": unknown,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate", "compile", "list", "due", "next"), default="validate")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        schema = _parse_json((root / SCHEMA_PATH).read_text(encoding="utf-8"), "schema")
        if args.command == "compile":
            registry = compile_registry(root)
        else:
            registry = _parse_json((root / REGISTRY_PATH).read_text(encoding="utf-8"), "registry")
        result = validate(root, registry, schema)
        if args.command == "compile":
            # Preserve prior outputs when the candidate fails validation.
            write_surfaces(root, registry)
        if args.command == "list":
            result = {"status": "VALID", "opportunities": registry["opportunities"], "counts": registry["counts"]}
        elif args.command == "due":
            result = _due(registry)
        elif args.command == "next":
            result = _next(registry)
        elif args.command == "compile":
            result = {
                "status": "COMPILED",
                "opportunities": registry["counts"]["opportunities"],
                "registry": str(REGISTRY_PATH),
                "validation": "VALID",
            }
    except (RegistryError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("OPPORTUNITY REGISTRY INVALID: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
