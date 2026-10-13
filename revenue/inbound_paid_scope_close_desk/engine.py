"""Evidence-bound inbound paid-scope owner-close compiler.

This module never sends, schedules, accepts, invoices, charges, or recognizes revenue.
Its strongest state is READY_FOR_OWNER_CLOSE: an internal human-review state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "inbound-paid-scope-close-desk/input/v1"
PACKET_SCHEMA = "inbound-paid-scope-close-desk/packet/v1"
RECEIPT_SCHEMA = "inbound-paid-scope-close-desk/receipt/v1"
TRUTH_BOUNDARY = "INTERNAL_OWNER_CLOSE_REVIEW_ONLY"
CURRENTNESS_BASIS = "OWNER_SUPPLIED_EVALUATION_TIME_NOT_PROVIDER_CLOCK"
EVIDENCE_AUTH = "CURATED_RECEIPT_METADATA_NOT_LIVE_PROVIDER_AUTHENTICATED"

EVENT_CLASSES = {
    "HUMAN_SCOPE_REQUEST",
    "HUMAN_POSITIVE",
    "AUTO_ACK",
    "SUPPORT_TICKET",
    "BOUNCE",
    "SILENCE",
    "DNR",
    "AMBIGUOUS",
}
SENDER_ROLES = {"EXTERNAL_HUMAN", "AUTOMATION", "SYSTEM", "UNKNOWN"}
SOURCE_AUTHORITIES = {"PROVIDER_RECEIPT", "CURATED_EXPORT", "SYNTHETIC_FIXTURE"}
CAPABILITY_STATUSES = {"VERIFIED", "OWNER_ONLY", "MISSING", "EXPIRED", "UNKNOWN"}
QUALIFICATION_STATUSES = {"PRIME_SUPPORTED", "PARTNER_ONLY", "HOLD_MISSING_EVIDENCE", "DISQUALIFIED"}
ROUTE_STATUSES = {"OPEN", "REPLY_ONLY", "HOLD", "BOUNCED", "DNR"}
COLLISION_STATES = {"CLEAR", "ACTIVE_OTHER_OWNER", "UNKNOWN", "DNR"}
MUSE_STATUSES = {"UNREQUESTED", "PENDING", "SELECTED", "DENIED", "STALE"}
COMMERCIAL_STATES = {"PROPOSED_NOT_ACCEPTED"}

TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CURRENCY = re.compile(r"^[A-Z]{3}$")


class CloseDeskError(ValueError):
    pass


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise CloseDeskError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_number(value):
    raise CloseDeskError(f"non-integer JSON number forbidden: {value}")


def load_json(raw: bytes, label: str = "input") -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise CloseDeskError(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CloseDeskError(f"{label}: BOM forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_bad_number,
            parse_constant=_bad_number,
        )
    except CloseDeskError:
        raise
    except Exception as exc:
        raise CloseDeskError(f"{label}: invalid JSON/UTF-8") from exc
    if not isinstance(value, dict):
        raise CloseDeskError(f"{label}: object required")
    return value


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(value: Any, wanted: list[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(wanted):
        raise CloseDeskError(f"{where}: keys mismatch")


def _string(value: Any, where: str, *, token: bool = False, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise CloseDeskError(f"{where}: invalid string")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise CloseDeskError(f"{where}: control character")
    if token and not TOKEN.fullmatch(value):
        raise CloseDeskError(f"{where}: invalid token")
    return value


def _integer(value: Any, where: str, lo: int = 0, hi: int = 10**15) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise CloseDeskError(f"{where}: integer required")
    return value


def _boolean(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise CloseDeskError(f"{where}: bool required")
    return value


def _sha(value: Any, where: str) -> str:
    value = _string(value, where, limit=64)
    if not SHA256.fullmatch(value):
        raise CloseDeskError(f"{where}: sha256 required")
    return value


def _timestamp(value: Any, where: str) -> str:
    value = _string(value, where, limit=20)
    try:
        if not UTC_SECOND.fullmatch(value):
            raise ValueError
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CloseDeskError(f"{where}: UTC second timestamp required") from exc
    return value


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _age_seconds(now: str, observed: str, where: str) -> int:
    age = int((_dt(now) - _dt(observed)).total_seconds())
    if age < 0:
        raise CloseDeskError(f"{where}: future timestamp")
    return age


def _list_strings(value: Any, where: str, *, min_items: int = 0, max_items: int = 64, token: bool = False) -> list[str]:
    if not isinstance(value, list) or not min_items <= len(value) <= max_items:
        raise CloseDeskError(f"{where}: invalid list")
    out = [_string(item, f"{where}[{i}]", token=token, limit=512) for i, item in enumerate(value)]
    if len(out) != len(set(out)):
        raise CloseDeskError(f"{where}: duplicate item")
    return out


def _enum(value: Any, choices: set[str], where: str) -> str:
    value = _string(value, where, token=True, limit=64)
    if value not in choices:
        raise CloseDeskError(f"{where}: unsupported value")
    return value


def authority_flags() -> dict[str, bool]:
    return {
        "external_send_authorized": False,
        "email_or_dm_authorized": False,
        "comment_or_form_authorized": False,
        "contract_or_signature_authorized": False,
        "buyer_acceptance_recognized": False,
        "invoice_authorized": False,
        "payment_authorized": False,
        "cash_or_revenue_recognized": False,
        "deployment_authorized": False,
        "scheduling_authorized": False,
    }


def normalize(value: dict[str, Any]) -> dict[str, Any]:
    _keys(
        value,
        [
            "schema",
            "truth_boundary",
            "case_id",
            "evaluation_time",
            "max_event_age_seconds",
            "max_evidence_age_seconds",
            "fixture",
            "event",
            "offer",
            "capability_evidence",
            "qualification",
            "route",
            "muse",
            "prior_touch",
        ],
        "input",
    )
    if value["schema"] != INPUT_SCHEMA or value["truth_boundary"] != TRUTH_BOUNDARY:
        raise CloseDeskError("input: unsupported schema/truth boundary")

    now = _timestamp(value["evaluation_time"], "evaluation_time")
    max_event_age = _integer(value["max_event_age_seconds"], "max_event_age_seconds", 1, 31_536_000)
    max_evidence_age = _integer(value["max_evidence_age_seconds"], "max_evidence_age_seconds", 1, 315_360_000)
    fixture = _boolean(value["fixture"], "fixture")
    case_id = _string(value["case_id"], "case_id", token=True)

    event = value["event"]
    _keys(
        event,
        [
            "event_id",
            "provider",
            "conversation_id",
            "message_id",
            "observed_at",
            "sender_role",
            "event_class",
            "source_authority",
            "source_uri",
            "source_sha256",
            "text_sha256",
        ],
        "event",
    )
    event_class = _enum(event["event_class"], EVENT_CLASSES, "event.event_class")
    sender_role = _enum(event["sender_role"], SENDER_ROLES, "event.sender_role")
    source_authority = _enum(event["source_authority"], SOURCE_AUTHORITIES, "event.source_authority")
    observed_at = _timestamp(event["observed_at"], "event.observed_at")
    event_age = _age_seconds(now, observed_at, "event.observed_at")
    normalized_event = {
        "event_id": _string(event["event_id"], "event.event_id", token=True),
        "provider": _string(event["provider"], "event.provider", token=True),
        "conversation_id": _string(event["conversation_id"], "event.conversation_id", token=True),
        "message_id": _string(event["message_id"], "event.message_id", token=True),
        "observed_at": observed_at,
        "sender_role": sender_role,
        "event_class": event_class,
        "source_authority": source_authority,
        "source_uri": _string(event["source_uri"], "event.source_uri", limit=2048),
        "source_sha256": _sha(event["source_sha256"], "event.source_sha256"),
        "text_sha256": _sha(event["text_sha256"], "event.text_sha256"),
        "stale": event_age > max_event_age,
    }

    offer = value["offer"]
    _keys(
        offer,
        [
            "offer_id",
            "observed_at",
            "source_uri",
            "source_sha256",
            "commercial_state",
            "currency",
            "fixed_amount_minor",
            "deliverables",
            "acceptance_questions",
            "exclusions",
        ],
        "offer",
    )
    offer_observed = _timestamp(offer["observed_at"], "offer.observed_at")
    offer_age = _age_seconds(now, offer_observed, "offer.observed_at")
    currency = _string(offer["currency"], "offer.currency", limit=3)
    if not CURRENCY.fullmatch(currency):
        raise CloseDeskError("offer.currency: uppercase ISO-like code required")
    normalized_offer = {
        "offer_id": _string(offer["offer_id"], "offer.offer_id", token=True),
        "observed_at": offer_observed,
        "source_uri": _string(offer["source_uri"], "offer.source_uri", limit=2048),
        "source_sha256": _sha(offer["source_sha256"], "offer.source_sha256"),
        "commercial_state": _enum(offer["commercial_state"], COMMERCIAL_STATES, "offer.commercial_state"),
        "currency": currency,
        "fixed_amount_minor": _integer(offer["fixed_amount_minor"], "offer.fixed_amount_minor", 1, 10**12),
        "deliverables": _list_strings(offer["deliverables"], "offer.deliverables", min_items=1, max_items=32),
        "acceptance_questions": _list_strings(
            offer["acceptance_questions"], "offer.acceptance_questions", min_items=1, max_items=32
        ),
        "exclusions": _list_strings(offer["exclusions"], "offer.exclusions", min_items=1, max_items=32),
        "stale": offer_age > max_evidence_age,
    }

    evidence = value["capability_evidence"]
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 64:
        raise CloseDeskError("capability_evidence: non-empty list required")
    normalized_evidence = []
    ids = set()
    for index, item in enumerate(evidence):
        where = f"capability_evidence[{index}]"
        _keys(
            item,
            ["evidence_id", "observed_at", "source_uri", "source_sha256", "status", "claim", "public"],
            where,
        )
        evidence_id = _string(item["evidence_id"], where + ".evidence_id", token=True)
        if evidence_id in ids:
            raise CloseDeskError("capability_evidence: duplicate evidence_id")
        ids.add(evidence_id)
        ev_observed = _timestamp(item["observed_at"], where + ".observed_at")
        ev_age = _age_seconds(now, ev_observed, where + ".observed_at")
        status = _enum(item["status"], CAPABILITY_STATUSES, where + ".status")
        if status == "VERIFIED" and ev_age > max_evidence_age:
            status = "EXPIRED"
        normalized_evidence.append(
            {
                "evidence_id": evidence_id,
                "observed_at": ev_observed,
                "source_uri": _string(item["source_uri"], where + ".source_uri", limit=2048),
                "source_sha256": _sha(item["source_sha256"], where + ".source_sha256"),
                "status": status,
                "claim": _string(item["claim"], where + ".claim", limit=1024),
                "public": _boolean(item["public"], where + ".public"),
            }
        )
    normalized_evidence.sort(key=lambda item: item["evidence_id"])

    qualification = value["qualification"]
    _keys(qualification, ["status", "source_uri", "source_sha256", "observed_at", "gaps"], "qualification")
    qual_observed = _timestamp(qualification["observed_at"], "qualification.observed_at")
    qual_age = _age_seconds(now, qual_observed, "qualification.observed_at")
    normalized_qualification = {
        "status": _enum(qualification["status"], QUALIFICATION_STATUSES, "qualification.status"),
        "source_uri": _string(qualification["source_uri"], "qualification.source_uri", limit=2048),
        "source_sha256": _sha(qualification["source_sha256"], "qualification.source_sha256"),
        "observed_at": qual_observed,
        "gaps": _list_strings(qualification["gaps"], "qualification.gaps", max_items=32),
        "stale": qual_age > max_evidence_age,
    }

    route = value["route"]
    _keys(
        route,
        [
            "status",
            "provider",
            "canonical_opportunity_key",
            "recipient_key",
            "action_key",
            "collision_state",
            "source_uri",
            "source_sha256",
            "observed_at",
        ],
        "route",
    )
    route_observed = _timestamp(route["observed_at"], "route.observed_at")
    route_age = _age_seconds(now, route_observed, "route.observed_at")
    normalized_route = {
        "status": _enum(route["status"], ROUTE_STATUSES, "route.status"),
        "provider": _string(route["provider"], "route.provider", token=True),
        "canonical_opportunity_key": _string(
            route["canonical_opportunity_key"], "route.canonical_opportunity_key", token=True
        ),
        "recipient_key": _string(route["recipient_key"], "route.recipient_key", token=True),
        "action_key": _string(route["action_key"], "route.action_key", token=True),
        "collision_state": _enum(route["collision_state"], COLLISION_STATES, "route.collision_state"),
        "source_uri": _string(route["source_uri"], "route.source_uri", limit=2048),
        "source_sha256": _sha(route["source_sha256"], "route.source_sha256"),
        "observed_at": route_observed,
        "stale": route_age > max_event_age,
    }

    muse = value["muse"]
    _keys(
        muse,
        [
            "status",
            "election_id",
            "canonical_opportunity_key",
            "action_key",
            "selected_sender_id",
            "observed_at",
            "expires_at",
            "source_uri",
            "source_sha256",
        ],
        "muse",
    )
    muse_status = _enum(muse["status"], MUSE_STATUSES, "muse.status")
    muse_observed = _timestamp(muse["observed_at"], "muse.observed_at")
    _age_seconds(now, muse_observed, "muse.observed_at")
    expires_at = _timestamp(muse["expires_at"], "muse.expires_at")
    if _dt(expires_at) < _dt(muse_observed):
        raise CloseDeskError("muse.expires_at: before observed_at")
    normalized_muse = {
        "status": muse_status,
        "election_id": _string(muse["election_id"], "muse.election_id", token=True),
        "canonical_opportunity_key": _string(
            muse["canonical_opportunity_key"], "muse.canonical_opportunity_key", token=True
        ),
        "action_key": _string(muse["action_key"], "muse.action_key", token=True),
        "selected_sender_id": _string(muse["selected_sender_id"], "muse.selected_sender_id", token=True),
        "observed_at": muse_observed,
        "expires_at": expires_at,
        "source_uri": _string(muse["source_uri"], "muse.source_uri", limit=2048),
        "source_sha256": _sha(muse["source_sha256"], "muse.source_sha256"),
        "expired": _dt(now) > _dt(expires_at),
    }

    prior = value["prior_touch"]
    _keys(prior, ["state", "contact_count", "last_contact_at", "last_action_key", "source_uri", "source_sha256"], "prior_touch")
    state = _enum(prior["state"], COLLISION_STATES, "prior_touch.state")
    count = _integer(prior["contact_count"], "prior_touch.contact_count", 0, 100000)
    last_contact = prior["last_contact_at"]
    if last_contact is not None:
        last_contact = _timestamp(last_contact, "prior_touch.last_contact_at")
        _age_seconds(now, last_contact, "prior_touch.last_contact_at")
    elif count:
        raise CloseDeskError("prior_touch: nonzero contact_count requires last_contact_at")
    last_action = prior["last_action_key"]
    if last_action is not None:
        last_action = _string(last_action, "prior_touch.last_action_key", token=True)
    elif count:
        raise CloseDeskError("prior_touch: nonzero contact_count requires last_action_key")
    normalized_prior = {
        "state": state,
        "contact_count": count,
        "last_contact_at": last_contact,
        "last_action_key": last_action,
        "source_uri": _string(prior["source_uri"], "prior_touch.source_uri", limit=2048),
        "source_sha256": _sha(prior["source_sha256"], "prior_touch.source_sha256"),
    }

    return {
        "case_id": case_id,
        "evaluation_time": now,
        "fixture": fixture,
        "event": normalized_event,
        "offer": normalized_offer,
        "capability_evidence": normalized_evidence,
        "qualification": normalized_qualification,
        "route": normalized_route,
        "muse": normalized_muse,
        "prior_touch": normalized_prior,
    }


def _decision(n: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    actions: list[str] = []
    event = n["event"]
    offer = n["offer"]
    evidence = n["capability_evidence"]
    qualification = n["qualification"]
    route = n["route"]
    muse = n["muse"]
    prior = n["prior_touch"]

    if n["fixture"]:
        return "HOLD_SYNTHETIC", ["fixture input cannot establish live human interest"], ["replace fixture with retained provider/thread evidence"]

    if event["event_class"] == "DNR" or route["status"] == "DNR" or route["collision_state"] == "DNR" or prior["state"] == "DNR":
        return "DNR", ["do-not-contact state present"], ["do not send or request a Muse election"]

    human = (
        event["event_class"] in {"HUMAN_SCOPE_REQUEST", "HUMAN_POSITIVE"}
        and event["sender_role"] == "EXTERNAL_HUMAN"
        and event["source_authority"] == "PROVIDER_RECEIPT"
        and not event["stale"]
    )
    if not human:
        blockers.append("no fresh provider-receipt-backed external human scope/positive event")
        if event["event_class"] in {"AUTO_ACK", "SUPPORT_TICKET", "BOUNCE", "SILENCE", "AMBIGUOUS"}:
            blockers.append(f"{event['event_class']} is not human interest")
        actions.append("obtain or retain an exact provider/thread receipt for genuine human scope intent")
        return "HOLD_SCOPE", blockers, actions

    if (
        route["status"] not in {"OPEN", "REPLY_ONLY"}
        or route["collision_state"] != "CLEAR"
        or prior["state"] != "CLEAR"
        or route["stale"]
        or route["provider"] != event["provider"]
    ):
        blockers.append("route/collision evidence is not a fresh clear reply path for this provider")
        actions.append("refresh route + prior-touch collision census before any response")
        return "HOLD_ROUTE", blockers, actions

    evidence_bad = [item["evidence_id"] for item in evidence if item["status"] != "VERIFIED"]
    if (
        offer["stale"]
        or qualification["stale"]
        or qualification["status"] not in {"PRIME_SUPPORTED", "PARTNER_ONLY"}
        or evidence_bad
    ):
        if offer["stale"]:
            blockers.append("current offer evidence is stale")
        if qualification["stale"]:
            blockers.append("qualification evidence is stale")
        if qualification["status"] not in {"PRIME_SUPPORTED", "PARTNER_ONLY"}:
            blockers.append(f"qualification state {qualification['status']} is not close-ready")
        if evidence_bad:
            blockers.append("capability evidence not VERIFIED: " + ", ".join(evidence_bad))
        actions.append("refresh/close evidence and qualification gaps before pricing or scope reply")
        return "HOLD_EVIDENCE", blockers, actions

    muse_exact = (
        muse["status"] == "SELECTED"
        and not muse["expired"]
        and muse["canonical_opportunity_key"] == route["canonical_opportunity_key"]
        and muse["action_key"] == route["action_key"]
    )
    if not muse_exact:
        blockers.append("fresh exact Muse single-writer selection is absent or mismatched")
        actions.append(
            f"request/refresh Muse election for {route['canonical_opportunity_key']} × {route['action_key']} immediately before send"
        )
        return "HOLD_MUSE", blockers, actions

    actions.extend(
        [
            "owner reviews bounded scope, offer, exclusions, qualification posture, and acceptance questions",
            "immediately before any external send, re-census route/prior-touch and re-confirm the exact Muse election",
            "a separate send-capable adapter must independently authorize and execute any response",
        ]
    )
    return "READY_FOR_OWNER_CLOSE", blockers, actions


def _public_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": item["evidence_id"],
            "claim": item["claim"],
            "observed_at": item["observed_at"],
            "source_sha256": item["source_sha256"],
        }
        for item in evidence
        if item["public"] and item["status"] == "VERIFIED"
    ]


def compile_bundle(raw: bytes) -> tuple[bytes, bytes, bytes]:
    n = normalize(load_json(raw))
    decision, blockers, owner_actions = _decision(n)
    packet = {
        "schema": PACKET_SCHEMA,
        "truth_boundary": TRUTH_BOUNDARY,
        "currentness_basis": CURRENTNESS_BASIS,
        "evidence_authentication": EVIDENCE_AUTH,
        "case_id": n["case_id"],
        "evaluation_time": n["evaluation_time"],
        "decision": decision,
        "blockers": blockers,
        "owner_actions": owner_actions,
        "event": {
            key: n["event"][key]
            for key in [
                "event_id",
                "provider",
                "conversation_id",
                "message_id",
                "observed_at",
                "sender_role",
                "event_class",
                "source_authority",
                "source_sha256",
                "text_sha256",
                "stale",
            ]
        },
        "offer": {
            key: n["offer"][key]
            for key in [
                "offer_id",
                "observed_at",
                "source_sha256",
                "commercial_state",
                "currency",
                "fixed_amount_minor",
                "deliverables",
                "acceptance_questions",
                "exclusions",
                "stale",
            ]
        },
        "qualification": {
            "status": n["qualification"]["status"],
            "observed_at": n["qualification"]["observed_at"],
            "source_sha256": n["qualification"]["source_sha256"],
            "gaps": n["qualification"]["gaps"],
            "stale": n["qualification"]["stale"],
        },
        "route": {
            "status": n["route"]["status"],
            "provider": n["route"]["provider"],
            "canonical_opportunity_key": n["route"]["canonical_opportunity_key"],
            "recipient_key": n["route"]["recipient_key"],
            "action_key": n["route"]["action_key"],
            "collision_state": n["route"]["collision_state"],
            "observed_at": n["route"]["observed_at"],
            "source_sha256": n["route"]["source_sha256"],
            "stale": n["route"]["stale"],
        },
        "muse": {
            "status": n["muse"]["status"],
            "election_id": n["muse"]["election_id"],
            "canonical_opportunity_key": n["muse"]["canonical_opportunity_key"],
            "action_key": n["muse"]["action_key"],
            "selected_sender_id": n["muse"]["selected_sender_id"],
            "observed_at": n["muse"]["observed_at"],
            "expires_at": n["muse"]["expires_at"],
            "source_sha256": n["muse"]["source_sha256"],
            "expired": n["muse"]["expired"],
            "meaning": "single-writer coordination evidence only; never proof of send, acceptance, payment, or revenue",
        },
        "prior_touch": n["prior_touch"],
        "public_capability_evidence": _public_evidence(n["capability_evidence"]),
        "private_capability_evidence_count": sum(1 for item in n["capability_evidence"] if not item["public"]),
        "authority": authority_flags(),
    }
    packet_bytes = canonical_json(packet)
    markdown_bytes = render_markdown(packet)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "truth_boundary": TRUTH_BOUNDARY,
        "case_id": n["case_id"],
        "decision": decision,
        "input_sha256": sha256(raw),
        "packet_sha256": sha256(packet_bytes),
        "markdown_sha256": sha256(markdown_bytes),
        "authority": authority_flags(),
    }
    return packet_bytes, markdown_bytes, canonical_json(receipt)


def _money(minor: int, currency: str) -> str:
    return f"{currency} {minor // 100:,}.{minor % 100:02d}"


def render_markdown(packet: dict[str, Any]) -> bytes:
    offer = packet["offer"]
    lines = [
        "# Inbound paid-scope owner-close packet",
        "",
        "> **INTERNAL OWNER REVIEW — NOT AUTHORIZED TO SEND.**",
        "> Muse selection coordinates one writer only. It is not evidence that a message was sent.",
        "",
        f"- Decision: **{packet['decision']}**",
        f"- Case: `{packet['case_id']}`",
        f"- Opportunity key: `{packet['route']['canonical_opportunity_key']}`",
        f"- Action key: `{packet['route']['action_key']}`",
        f"- Human-event class: `{packet['event']['event_class']}`",
        f"- Proposed offer: `{offer['offer_id']}` · {_money(offer['fixed_amount_minor'], offer['currency'])} · `{offer['commercial_state']}`",
        f"- Qualification: `{packet['qualification']['status']}`",
        f"- Muse: `{packet['muse']['status']}` / `{packet['muse']['election_id']}`",
        "",
        "## Bounded scope",
        "",
    ]
    lines.extend(f"- {item}" for item in offer["deliverables"])
    lines += ["", "### Exclusions", ""]
    lines.extend(f"- {item}" for item in offer["exclusions"])
    lines += ["", "## Acceptance questions", ""]
    lines.extend(f"- {item}" for item in offer["acceptance_questions"])
    lines += ["", "## Public delivery/capability evidence", ""]
    if packet["public_capability_evidence"]:
        for item in packet["public_capability_evidence"]:
            lines.append(f"- `{item['evidence_id']}` — {item['claim']} · `{item['source_sha256']}`")
    else:
        lines.append("- None admissible for buyer-facing use.")
    if packet["private_capability_evidence_count"]:
        lines.append(f"- `{packet['private_capability_evidence_count']}` private evidence item(s) intentionally omitted.")
    if packet["blockers"]:
        lines += ["", "## Holds", ""]
        lines.extend(f"- {item}" for item in packet["blockers"])
    lines += ["", "## Owner actions", ""]
    lines.extend(f"- {item}" for item in packet["owner_actions"])
    lines += [
        "",
        "## Authority ceiling",
        "",
        "- External send: **false**",
        "- Contract/signature or buyer acceptance: **false**",
        "- Invoice/payment/cash/revenue recognition: **false**",
        "- Deployment/scheduling: **false**",
        "",
        f"Currentness basis: `{packet['currentness_basis']}`.",
        f"Evidence authentication: `{packet['evidence_authentication']}`.",
    ]
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def verify_bundle(raw: bytes, packet_bytes: bytes, markdown_bytes: bytes, receipt_bytes: bytes) -> str:
    expected = compile_bundle(raw)
    if (packet_bytes, markdown_bytes, receipt_bytes) != expected:
        raise CloseDeskError("bundle mismatch")
    packet = load_json(packet_bytes, "packet")
    receipt = load_json(receipt_bytes, "receipt")
    if packet.get("schema") != PACKET_SCHEMA or receipt.get("schema") != RECEIPT_SCHEMA:
        raise CloseDeskError("bundle schema mismatch")
    if packet.get("authority") != authority_flags() or receipt.get("authority") != authority_flags():
        raise CloseDeskError("authority mismatch")
    return "EXACT_OWNER_CLOSE_MATCH"


def _preflight_outputs(paths: list[Path]) -> None:
    if len({str(path.absolute()) for path in paths}) != len(paths):
        raise CloseDeskError("output paths must be distinct")
    for path in paths:
        if path.exists() or path.is_symlink():
            raise CloseDeskError(f"output exists: {path}")
        if not path.parent.exists() or not path.parent.is_dir():
            raise CloseDeskError(f"output parent missing: {path.parent}")


def _publish_atomic(outputs: list[tuple[Path, bytes]]) -> None:
    paths = [path for path, _ in outputs]
    _preflight_outputs(paths)
    staged: list[Path] = []
    published: list[Path] = []
    try:
        for path, data in outputs:
            fd, tmp_name = tempfile.mkstemp(prefix=".close-desk-", dir=str(path.parent))
            tmp = Path(tmp_name)
            staged.append(tmp)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        for (path, _), tmp in zip(outputs, staged):
            os.link(tmp, path)
            published.append(path)
    except Exception:
        for path in reversed(published):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for tmp in staged:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inbound-paid-scope-close-desk")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("input")
    compile_parser.add_argument("--packet", required=True)
    compile_parser.add_argument("--markdown", required=True)
    compile_parser.add_argument("--receipt", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("input")
    verify_parser.add_argument("packet")
    verify_parser.add_argument("markdown")
    verify_parser.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            raw = Path(args.input).read_bytes()
            packet, markdown, receipt = compile_bundle(raw)
            _publish_atomic(
                [
                    (Path(args.packet), packet),
                    (Path(args.markdown), markdown),
                    (Path(args.receipt), receipt),
                ]
            )
            sys.stdout.write(load_json(packet, "packet")["decision"] + "\n")
            return 0
        token = verify_bundle(
            Path(args.input).read_bytes(),
            Path(args.packet).read_bytes(),
            Path(args.markdown).read_bytes(),
            Path(args.receipt).read_bytes(),
        )
        sys.stdout.write(token + "\n")
        return 0
    except (CloseDeskError, OSError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


def main() -> None:
    raise SystemExit(_cli())


if __name__ == "__main__":
    main()
