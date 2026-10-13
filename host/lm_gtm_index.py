#!/usr/bin/env python3
"""LLM-native compose/query layer over existing Commons GTM ledgers.

This is not a CRM. Canonical records stay in Airtable
`JOJO Revenue Recovery CRM / Revenue Pipeline` and the in-repo ledgers this
tool reads. The public artifact is one index-first projection plus an
append-only overlay of events that cite existing subject ids.

It does not mint crm/, people/, contacts/, sales/, accounts, or deals.
It does not rewrite website-people-email-book loop.json schema v2.
Live send is refused. Cash stays USD 0 without payment evidence.

Agent floor: `python3 host/lm_gtm_index.py brief` lists compact HOT
rows. `sent` lists HARD_DO_NOT_RESEND including bounced DNR.
OWNER_HOLD is live and not hot. Occupancy (`claim` / `release`)
IS admission for sales/draft/outreach. Brief remains the floor for
listing. Still not a second CRM. It does not rewrite loop.json.
`--send` exits 3. Unclaimed sales exit 4.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "commons-lm-gtm-index/v1"
KIND_STATE = "LM_GTM_INDEX_STATE"
KIND_HEADER = "LM_GTM_INDEX_HEADER"
KIND_ROW = "LM_GTM_INDEX_ROW"
KIND_EVENT = "LM_GTM_OVERLAY_EVENT"
INDEX_REL = "revenue/lm_gtm_index/INDEX.jsonl"
EVENTS_REL = "revenue/lm_gtm_index/events.jsonl"
CANONICAL_CRM = "JOJO Revenue Recovery CRM / Revenue Pipeline"
SUBJECT_RE = re.compile(r"^[A-Za-z0-9._-]{3,80}$")
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
EMAIL_AT_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_RE = re.compile(r"(?:\+?1[\s.-])?(?:\(?\d{3}\)?[\s.-])\d{3}[\s.-]\d{4}")
POINTER_TYPES = frozenset(
    {"MATERIAL_REPLY", "SENT_AWAITING_REPLY", "VERIFIED_LEAD_UNSENT", "HOLD_BUILD_AND_VERIFY"}
)
OCCUPANCY_TYPES = frozenset({"CLAIM", "RELEASE", "STEAL"})
NOTE_TYPE = "NOTE"
STATUS_TYPE = "STATUS"
ALLOWED_EVENT_TYPES = POINTER_TYPES | OCCUPANCY_TYPES | {NOTE_TYPE, STATUS_TYPE}
LIVE_ROLES = frozenset({"external_prospect", "inbound_contact"})
HOLD_DECISIONS = frozenset({"HOLD_DO_NOT_RESEND", "HOLD_DO_NOT_CONTACT"})
OWNER_HOLD_DECISIONS = frozenset({"OWNER_HOLD", "DNR_OUTREACH", "NOT_HOT"})
SENT_DNR_DECISIONS = frozenset({"SENT_AWAITING_REPLY", "BOUNCED"})
HOLD_BUILD_DECISION = "HOLD_BUILD_AND_VERIFY"
STALE_AFTER = dt.timedelta(hours=12)
STALE_WARNING = "overlay composed_at older than 12h; re-verify Slack before acting"
DUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HOT_RANK = {
    "material_reply": 0,
    "sent_awaiting_reply": 1,
    "ready_to_draft": 2,
    "verified_lead_unsent": 3,
}
ROLE_ORDER = {
    "external_prospect": 0,
    "inbound_contact": 1,
    "seller_context": 2,
    "research_universe": 3,
    "mailbox_manifest": 4,
}
ROW_KEYS = {
    "schema_version",
    "kind",
    "id",
    "role",
    "live",
    "organization",
    "source_ledgers",
    "source_paths",
    "route_kind",
    "route_ref",
    "decision",
    "next_action",
    "due",
    "owner",
    "dnr",
    "occupied_by",
    "overlay_event_ids",
    "cash_usd",
    "person",
}
DOES_NOT_REPLACE = [
    "revenue/website_people_email_book",
    "revenue/smart_outreach",
    "revenue/marketing_sales",
    "revenue/reply_to_revenue",
    "revenue/payment_ready/outreach_receipts",
    "revenue/swarm_mail",
    "Airtable JOJO Revenue Recovery CRM / Revenue Pipeline",
]
DOES_NOT_CREATE = ["crm/", "people/", "contacts/", "sales/"]
BRIEF_FIELDS = (
    "id",
    "lane",
    "organization",
    "person",
    "decision",
    "next_action",
    "dnr",
    "owner",
    "due",
    "route_ref",
    "source",
)
BRIEF_HEADER_KEYS = frozenset(
    {
        "hot",
        "hold",
        "sent_dnr",
        "occupied",
        "cash_usd",
        "canonical_crm",
        "composed_at",
        "stale_warning",
        "mailbox",
    }
)
NEEDS_OWNER_MAILBOX = "NEEDS_OWNER_MAILBOX"
COMPOSE = {
    "website_people_email_book": "external prospects vs seller contacts; drafts only; --send exits 3",
    "smart_outreach": "evidence-bound candidates; does not open a second CRM",
    "reply_to_revenue": "inbound cash truth; never opens a second CRM",
    "marketing_sales": "public research universe; Airtable remains canonical CRM",
    "outreach_receipts": "DNR / collision receipts; not a contact book",
    "swarm_mail": "public inbox manifest; private addresses stay off git",
    "lm_gtm_overlay": "pointer events for live sales surfaces; occupancy overlay; STATUS refresh of decision/dnr/due; OWNER_HOLD; BOUNCED DNR; HOLD_BUILD_AND_VERIFY; not a contact book",
}
# TOKEN placeholders (SUBJECT, YOU, EVENT_ID, NOTE) survive JSON, markdown, and HTML.
# Flag --subject still works; --owner is still required. list_* and open_by_ref stay as-is.
CONTRACT = {
    "read_index": "revenue/lm_gtm_index/INDEX.jsonl",
    "read_state": "revenue/lm_gtm_index/state.json",
    "list_brief": "python3 host/lm_gtm_index.py brief",
    "check_freshness": "python3 host/lm_gtm_index.py freshness",
    "mailbox_verify": "python3 host/lm_gtm_mailbox_buyer_reply_verify.py SUBJECT",
    "handoff_mailbox_verify": "python3 host/lm_gtm_relationship_handoff.py SUBJECT --mailbox-verify",
    "list_next": "python3 host/lm_gtm_index.py next",
    "list_hot": "python3 host/lm_gtm_index.py hot",
    "list_hold": "python3 host/lm_gtm_index.py hold",
    "list_sent": "python3 host/lm_gtm_index.py sent",
    "open_by_ref": "python3 host/lm_gtm_index.py show <existing-id> [--sources]",
    "append_event": 'python3 host/lm_gtm_index.py append-event --subject SUBJECT --id EVENT_ID --body "NOTE"',
    "claim": "python3 host/lm_gtm_index.py claim SUBJECT --owner YOU",
    "release": "python3 host/lm_gtm_index.py release SUBJECT --owner YOU",
    "require-claim": "python3 host/lm_gtm_index.py require-claim SUBJECT --owner YOU",
    "send": "illegal; exits 3",
    "mailbox_send": "illegal; exits 3",
    "sales_without_claim": "illegal; exits 4",
}


class IndexError_(ValueError):
    """Projection, overlay, or lookup failed closed."""


class SendError(IndexError_):
    """Live send was requested. This composer never transports mail."""


class UnclaimedSales(Exception):
    """Sales/draft/outreach without a live occupant matching --owner."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def default_paths(root: Path = ROOT) -> dict[str, Path]:
    base = root / "revenue" / "lm_gtm_index"
    return {
        "root": root,
        "loop": root / "revenue" / "website_people_email_book" / "loop.json",
        "candidates": root / "revenue" / "smart_outreach" / "candidates.json",
        "funnel": root / "revenue" / "reply_to_revenue" / "funnel.json",
        "pipeline": root / "revenue" / "marketing_sales" / "pipeline.json",
        "receipts": root / "revenue" / "payment_ready" / "outreach_receipts",
        "inboxes": root / "revenue" / "swarm_mail" / "inboxes.json",
        "index": base / "INDEX.jsonl",
        "state": base / "state.json",
        "events": base / "events.jsonl",
    }


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IndexError_(f"cannot read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise IndexError_(f"{path} must contain one JSON object")
    return value


def rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def parse_time(value: str) -> dt.datetime:
    if not isinstance(value, str):
        raise IndexError_(f"invalid date-time: {value}")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except (TypeError, ValueError) as error:
        raise IndexError_(f"invalid date-time: {value}") from error
    if parsed.tzinfo is None:
        raise IndexError_("date-time must include a timezone")
    try:
        return parsed.astimezone(dt.timezone.utc)
    except (OverflowError, ValueError) as error:
        raise IndexError_(f"invalid date-time: {value}") from error


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    # JSONL records use LF; Unicode line separators inside strings are data.
    for line_no, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise IndexError_(f"{path}:{line_no} is not JSONL: {error}") from error
        if not isinstance(item, dict):
            raise IndexError_(f"{path}:{line_no} must be a JSON object")
        rows.append(item)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")


def _blank_row(subject_id: str, role: str) -> dict[str, Any]:
    if not SUBJECT_RE.fullmatch(subject_id):
        raise IndexError_(f"illegal subject id: {subject_id}")
    live = role in {"external_prospect", "inbound_contact"}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_ROW,
        "id": subject_id,
        "role": role,
        "live": live,
        "organization": None,
        "source_ledgers": [],
        "source_paths": [],
        "route_kind": None,
        "route_ref": None,
        "decision": None,
        "next_action": None,
        "due": None,
        "owner": "UNSEATED",
        "dnr": False,
        "occupied_by": None,
        "overlay_event_ids": [],
        "cash_usd": 0,
        "person": None,
    }


def _touch(row: dict[str, Any], ledger: str, path: str) -> None:
    if ledger not in row["source_ledgers"]:
        row["source_ledgers"].append(ledger)
    if path not in row["source_paths"]:
        row["source_paths"].append(path)


def _route_from(source: dict[str, Any], row: dict[str, Any]) -> None:
    route = source.get("route")
    if not isinstance(route, dict):
        return
    kind = route.get("kind")
    if isinstance(kind, str) and kind:
        row["route_kind"] = kind
    if kind == "EXISTING_CRM_RECORD":
        value = route.get("value")
        if isinstance(value, str) and value.startswith("airtable:"):
            row["route_ref"] = value


def _assert_no_email_in_index_blob(blob: str) -> None:
    _assert_no_pii_in_index_blob(blob)


def _assert_no_pii_in_index_blob(blob: str) -> None:
    if EMAIL_AT_RE.search(blob):
        raise IndexError_("INDEX projection copied an email; keep emails in source ledgers")
    if PHONE_RE.search(blob):
        raise IndexError_("INDEX projection copied a phone number; keep phones in source ledgers")


def _assert_clean_pointer_text(value: Any, label: str) -> None:
    if value is None:
        return
    text = value if isinstance(value, str) else json.dumps(value)
    if EMAIL_AT_RE.search(text):
        raise IndexError_(f"{label} copied an email; keep emails in source ledgers")
    if PHONE_RE.search(text):
        raise IndexError_(f"{label} copied a phone number; keep phones in source ledgers")


def hot_class(row: dict[str, Any]) -> str | None:
    if row.get("role") not in LIVE_ROLES or not row.get("live"):
        return None
    decision = row.get("decision")
    if decision == HOLD_BUILD_DECISION or decision in OWNER_HOLD_DECISIONS or decision == "BOUNCED":
        return None
    if row.get("dnr") or decision in HOLD_DECISIONS:
        return None
    if decision == "MATERIAL_REPLY":
        return "material_reply"
    if decision == "SENT_AWAITING_REPLY":
        return "sent_awaiting_reply"
    if decision == "READY_TO_DRAFT":
        return "ready_to_draft"
    if decision == "VERIFIED_LEAD_UNSENT":
        return "verified_lead_unsent"
    return None


def hot_next_actions(paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    built = build_index(paths)
    ranked: list[dict[str, Any]] = []
    for row in built["rows"]:
        klass = hot_class(row)
        if klass is None:
            continue
        item = dict(row)
        item["hot_class"] = klass
        item["hot_rank"] = HOT_RANK[klass]
        ranked.append(item)
    ranked.sort(key=lambda row: (row["hot_rank"], row["id"]))
    return ranked


def hold_build_next_actions(paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    built = build_index(paths)
    rows = [
        row
        for row in built["rows"]
        if row.get("live") and row.get("decision") == HOLD_BUILD_DECISION
    ]
    rows.sort(key=lambda row: row["id"])
    return rows


def is_sent_dnr_row(row: dict[str, Any]) -> bool:
    return bool(row.get("live") and row.get("dnr") and row.get("decision") in SENT_DNR_DECISIONS)


def sent_awaiting_dnr_rows(paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    built = build_index(paths)
    rows = [row for row in built["rows"] if is_sent_dnr_row(row)]
    rows.sort(key=lambda row: row["id"])
    return rows


def compact_source(row: dict[str, Any]) -> str | None:
    paths = [item for item in (row.get("source_paths") or []) if isinstance(item, str) and item]
    def pick(predicate: Any) -> str | None:
        for path in paths:
            if predicate(path):
                return path
        return None

    return (
        pick(lambda path: path.endswith(".py"))
        or pick(lambda path: path.startswith("p/") and path.endswith(".md"))
        or pick(lambda path: path.startswith("slack:"))
        or pick(lambda path: path.startswith("airtable:") or (path.startswith("revenue/") and path != EVENTS_REL))
        or pick(lambda path: path != EVENTS_REL)
    )


def compact_lane(row: dict[str, Any]) -> str:
    klass = hot_class(row)
    if klass:
        return klass
    if row.get("decision") == "OWNER_HOLD":
        return "owner_hold"
    if row.get("decision") == "BOUNCED":
        return "bounced"
    if row.get("decision") == "SENT_AWAITING_REPLY" and row.get("dnr"):
        return "sent_dnr"
    if row.get("decision") == HOLD_BUILD_DECISION:
        return "hold_build"
    if row.get("dnr") or row.get("decision") in HOLD_DECISIONS | OWNER_HOLD_DECISIONS:
        return "dnr"
    if row.get("live"):
        return "live"
    return str(row.get("role") or "context")


def occupied_live_count(rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if row.get("live") and (row.get("owner") or "UNSEATED") != "UNSEATED"
    )


def compact_row(row: dict[str, Any], *, lane: str | None = None) -> dict[str, Any]:
    owner = row.get("owner") or "UNSEATED"
    dnr = bool(row.get("dnr"))
    item = {
        "id": row["id"],
        "lane": lane or compact_lane(row),
        "organization": row.get("organization"),
        "person": row.get("person"),
        "decision": row.get("decision"),
        "next_action": row.get("next_action"),
        "dnr": True if dnr else None,
        "owner": None if owner == "UNSEATED" else owner,
        "due": row.get("due"),
        "route_ref": row.get("route_ref"),
        "source": compact_source(row),
    }
    compact = {key: item[key] for key in BRIEF_FIELDS if item[key] is not None and item[key] != ""}
    blob = json.dumps(compact, sort_keys=True, ensure_ascii=False)
    _assert_no_pii_in_index_blob(blob)
    extra = set(compact) - set(BRIEF_FIELDS)
    if extra:
        raise IndexError_(f"compact row extra keys: {sorted(extra)}")
    return compact


def brief_header(
    paths: dict[str, Path] | None = None,
    built: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    built = built or build_index(paths)
    truth = built["state"]["truth"]
    composed = str(built["state"]["composed_at"])
    header = {
        "hot": int(truth["hot_next_actions"]),
        "hold": int(truth["hold_build_actions"]),
        "sent_dnr": int(truth["sent_awaiting_dnr_actions"]),
        "occupied": occupied_live_count(built["rows"]),
        "cash_usd": 0,
        "canonical_crm": CANONICAL_CRM,
        "composed_at": composed,
    }
    mailbox = truth.get("mailbox")
    if mailbox == NEEDS_OWNER_MAILBOX:
        header["mailbox"] = NEEDS_OWNER_MAILBOX
    instant = now or dt.datetime.now(dt.timezone.utc)
    if instant - parse_time(composed) > STALE_AFTER:
        header["stale_warning"] = STALE_WARNING
    extra = set(header) - BRIEF_HEADER_KEYS
    if extra:
        raise IndexError_(f"brief header extra keys: {sorted(extra)}")
    _assert_no_pii_in_index_blob(json.dumps(header, sort_keys=True, ensure_ascii=False))
    return header


def brief_hot_rows(paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    return [compact_row(row, lane=str(row["hot_class"])) for row in hot_next_actions(paths)]


def compact_sent_rows(paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    return [compact_row(row) for row in sent_awaiting_dnr_rows(paths)]


def compact_hold_rows(paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    return [compact_row(row, lane="hold_build") for row in hold_build_next_actions(paths)]


def emit_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)


def load_receipts(paths: dict[str, Path]) -> list[dict[str, Any]]:
    folder = paths["receipts"]
    if not folder.is_dir():
        raise IndexError_(f"missing receipts directory {folder}")
    loaded: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        receipt = read_object(path)
        target = receipt.get("target_id")
        if not isinstance(target, str) or not target:
            raise IndexError_(f"{path} missing target_id")
        dedupe = receipt.get("dedupe") if isinstance(receipt.get("dedupe"), dict) else {}
        loaded.append(
            {
                "target_id": target,
                "path": rel(paths["root"], path),
                "do_not_resend": bool(dedupe.get("do_not_resend")),
                "organization": receipt.get("organization"),
            }
        )
    return loaded


def load_events(paths: dict[str, Path]) -> list[dict[str, Any]]:
    events = load_jsonl(paths["events"])
    seen: set[str] = set()
    for event in events:
        if event.get("schema_version") != SCHEMA_VERSION or event.get("kind") != KIND_EVENT:
            raise IndexError_(f"overlay event {event.get('id')!r} is not {KIND_EVENT}")
        event_id = event.get("id")
        subject = event.get("subject_id")
        if not isinstance(event_id, str) or not EVENT_ID_RE.fullmatch(event_id):
            raise IndexError_(f"illegal overlay event id: {event_id}")
        if event_id in seen:
            raise IndexError_(f"overlay event remint refused: {event_id}")
        seen.add(event_id)
        if not isinstance(subject, str) or not SUBJECT_RE.fullmatch(subject):
            raise IndexError_(f"overlay event {event_id} missing subject_id")
        if event.get("cash_usd") != 0:
            raise IndexError_(f"overlay event {event_id} claimed cash")
        if event.get("transport") not in {None, "NONE"}:
            raise IndexError_(f"overlay event {event_id} claimed transport")
        parse_time(str(event.get("ts")))
        etype = event.get("type") or NOTE_TYPE
        if etype not in ALLOWED_EVENT_TYPES:
            raise IndexError_(f"overlay event {event_id} has illegal type {etype!r}")
        event["type"] = etype
        _assert_clean_pointer_text(event.get("organization"), f"overlay event {event_id} organization")
        _assert_clean_pointer_text(event.get("person"), f"overlay event {event_id} person")
        _assert_clean_pointer_text(event.get("next_action"), f"overlay event {event_id} next_action")
        _assert_clean_pointer_text(event.get("source_paths"), f"overlay event {event_id} source_paths")
        if etype in POINTER_TYPES:
            role = event.get("role")
            if role not in LIVE_ROLES:
                raise IndexError_(f"overlay event {event_id} cannot mint role {role!r}")
            organization = event.get("organization")
            if not isinstance(organization, str) or not organization.strip():
                raise IndexError_(f"overlay event {event_id} missing organization pointer")
            paths_value = event.get("source_paths")
            if not isinstance(paths_value, list) or not paths_value or not all(isinstance(item, str) and item for item in paths_value):
                raise IndexError_(f"overlay event {event_id} missing source_paths pointers")
            if etype == HOLD_BUILD_DECISION:
                person = event.get("person")
                if not isinstance(person, str) or not person.strip():
                    raise IndexError_(f"overlay event {event_id} missing person pointer")
        if etype == STATUS_TYPE:
            due = event.get("due")
            if due is not None and (not isinstance(due, str) or not DUE_RE.fullmatch(due)):
                raise IndexError_(f"overlay event {event_id} has illegal due {due!r}")
        if etype in OCCUPANCY_TYPES:
            owner = event.get("owner") or event.get("from")
            if not isinstance(owner, str) or not owner.strip():
                raise IndexError_(f"overlay event {event_id} occupancy missing owner")
            event["owner"] = owner.strip()
    return events


def apply_overlay_events(subjects: dict[str, dict[str, Any]], events: list[dict[str, Any]]) -> None:
    for event in events:
        etype = event.get("type") or NOTE_TYPE
        subject_id = event["subject_id"]
        if etype in POINTER_TYPES:
            existing = subjects.get(subject_id)
            if existing is None:
                existing = _blank_row(subject_id, str(event["role"]))
                subjects[subject_id] = existing
            row = existing
            if row["role"] not in LIVE_ROLES:
                raise IndexError_(f"overlay event cannot attach to {row['role']} {subject_id}")
            if row["role"] == "inbound_contact" and event.get("role") == "external_prospect":
                row["role"] = "external_prospect"
                row["live"] = True
            _touch(row, "lm_gtm_overlay", EVENTS_REL)
            for path in event.get("source_paths") or []:
                if path not in row["source_paths"]:
                    row["source_paths"].append(path)
            if event.get("organization") and not row["organization"]:
                row["organization"] = event["organization"]
            if event.get("person"):
                row["person"] = event["person"]
            if event.get("route_kind"):
                row["route_kind"] = event["route_kind"]
            if event.get("route_ref"):
                row["route_ref"] = event["route_ref"]
            if etype == "MATERIAL_REPLY":
                row["decision"] = "MATERIAL_REPLY"
                row["dnr"] = False
                row["live"] = True
            elif etype == "SENT_AWAITING_REPLY":
                row["decision"] = "SENT_AWAITING_REPLY"
                row["live"] = True
                if event.get("dnr") is True or event.get("decision") in HOLD_DECISIONS | {"HARD_DO_NOT_RESEND"}:
                    row["dnr"] = True
            elif etype == "VERIFIED_LEAD_UNSENT":
                row["decision"] = "VERIFIED_LEAD_UNSENT"
                row["dnr"] = False
                row["live"] = True
            elif etype == HOLD_BUILD_DECISION:
                row["decision"] = HOLD_BUILD_DECISION
                row["live"] = True
            if event.get("next_action"):
                row["next_action"] = event["next_action"]
        else:
            if subject_id not in subjects:
                raise IndexError_(
                    f"overlay event cites unknown subject {subject_id}; composer does not mint a contact book"
                )
            row = subjects[subject_id]
            if row["role"] not in LIVE_ROLES:
                raise IndexError_(f"overlay event cannot attach to {row['role']} {subject_id}")
            _touch(row, "lm_gtm_overlay", EVENTS_REL)
            if etype == STATUS_TYPE:
                for path in event.get("source_paths") or []:
                    if path not in row["source_paths"]:
                        row["source_paths"].append(path)
                if event.get("next_action"):
                    row["next_action"] = event["next_action"]
                if event.get("due"):
                    row["due"] = event["due"]
                if event.get("decision"):
                    row["decision"] = event["decision"]
                if event.get("dnr") is True:
                    row["dnr"] = True
                elif event.get("dnr") is False:
                    row["dnr"] = False
                if event.get("route_kind"):
                    row["route_kind"] = event["route_kind"]
                if event.get("route_ref"):
                    row["route_ref"] = event["route_ref"]
                if event.get("organization") and not row["organization"]:
                    row["organization"] = event["organization"]
            elif etype == "CLAIM" or etype == "STEAL":
                row["owner"] = event.get("owner") or event.get("from") or "UNSEATED"
            elif etype == "RELEASE":
                row["owner"] = "UNSEATED"
        if event["id"] not in row["overlay_event_ids"]:
            row["overlay_event_ids"].append(event["id"])


def compose_subjects(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    loop = read_object(paths["loop"])
    if loop.get("schema_version") != "commons-website-people-email-book/v2":
        raise IndexError_("website-people-email-book loop.json is not schema v2; do not rewrite it")
    candidates = read_object(paths["candidates"])
    funnel = read_object(paths["funnel"])
    pipeline = read_object(paths["pipeline"])
    inboxes = read_object(paths["inboxes"])
    receipts = load_receipts(paths)
    events = load_events(paths)
    subjects: dict[str, dict[str, Any]] = {}

    def row_for(subject_id: str, role: str) -> dict[str, Any]:
        existing = subjects.get(subject_id)
        if existing is None:
            existing = _blank_row(subject_id, role)
            subjects[subject_id] = existing
            return existing
        if existing["role"] == "seller_context" and role != "seller_context":
            raise IndexError_(f"{subject_id} is seller context and cannot become a prospect")
        if existing["role"] == "inbound_contact" and role == "external_prospect":
            existing["role"] = "external_prospect"
            existing["live"] = True
        return existing

    loop_rel = rel(paths["root"], paths["loop"])
    for prospect in loop.get("prospects") or []:
        if not isinstance(prospect, dict):
            raise IndexError_("loop.prospects entries must be objects")
        subject_id = prospect.get("prospect_id")
        if not isinstance(subject_id, str):
            raise IndexError_("loop prospect missing prospect_id")
        row = row_for(subject_id, "external_prospect")
        _touch(row, "website_people_email_book", loop_rel)
        row["organization"] = prospect.get("organization")
        row["decision"] = prospect.get("decision")
        row["next_action"] = prospect.get("next_action")
        row["occupied_by"] = prospect.get("occupied_by")
        if prospect.get("decision") in {"HOLD_DO_NOT_RESEND", "HOLD_DO_NOT_CONTACT"}:
            row["dnr"] = True
        _route_from(prospect, row)

    for seller in loop.get("seller_contacts") or []:
        if not isinstance(seller, dict):
            raise IndexError_("loop.seller_contacts entries must be objects")
        subject_id = seller.get("contact_id")
        if not isinstance(subject_id, str):
            raise IndexError_("seller contact missing contact_id")
        row = row_for(subject_id, "seller_context")
        _touch(row, "website_people_email_book", loop_rel)
        row["organization"] = "Commons seller fixture (not a buyer)"
        row["decision"] = "SELLER_CONTEXT_NOT_PROSPECT"
        row["next_action"] = seller.get("next_action")
        row["live"] = False
        _route_from(seller, row)
        row["route_ref"] = None

    cand_rel = rel(paths["root"], paths["candidates"])
    for prospect in candidates.get("prospects") or []:
        if not isinstance(prospect, dict):
            raise IndexError_("candidates.prospects entries must be objects")
        subject_id = prospect.get("prospect_id")
        if not isinstance(subject_id, str):
            raise IndexError_("candidate missing prospect_id")
        row = row_for(subject_id, "external_prospect")
        _touch(row, "smart_outreach", cand_rel)
        if not row["organization"]:
            row["organization"] = prospect.get("organization")
        if prospect.get("occupied_by") and not row["occupied_by"]:
            row["occupied_by"] = prospect.get("occupied_by")
        if prospect.get("do_not_contact"):
            row["dnr"] = True
        _route_from(prospect, row)

    funnel_rel = rel(paths["root"], paths["funnel"])
    for contact in funnel.get("contacts") or []:
        if not isinstance(contact, dict):
            raise IndexError_("funnel.contacts entries must be objects")
        subject_id = contact.get("prospect_key")
        if not isinstance(subject_id, str):
            raise IndexError_("funnel contact missing prospect_key")
        role = "external_prospect" if subject_id in subjects and subjects[subject_id]["role"] == "external_prospect" else "inbound_contact"
        row = row_for(subject_id, role)
        _touch(row, "reply_to_revenue", funnel_rel)
        if not row["organization"]:
            row["organization"] = contact.get("organization")
        if contact.get("hard_dnr"):
            row["dnr"] = True
        if not row["decision"]:
            row["decision"] = contact.get("lane")
        if not row["next_action"]:
            row["next_action"] = contact.get("next_action")
        if row["dnr"] and row["decision"] not in {
            "HOLD_DO_NOT_RESEND",
            "HOLD_DO_NOT_CONTACT",
            "SELLER_CONTEXT_NOT_PROSPECT",
        }:
            if not row["next_action"]:
                row["next_action"] = contact.get("next_action")

    for receipt in receipts:
        row = row_for(receipt["target_id"], "inbound_contact")
        _touch(row, "outreach_receipts", receipt["path"])
        if receipt["do_not_resend"]:
            row["dnr"] = True
        if not row["organization"] and receipt["organization"]:
            row["organization"] = receipt["organization"]
        if row["dnr"] and not row["decision"]:
            row["decision"] = "HOLD_DO_NOT_RESEND"
        if row["dnr"] and not row["next_action"]:
            row["next_action"] = "retain canonical receipt suppression; no draft and no transport handoff"

    research = _blank_row("marketing-sales-research-universe", "research_universe")
    pipe_rel = rel(paths["root"], paths["pipeline"])
    _touch(research, "marketing_sales", pipe_rel)
    current = pipeline.get("current") if isinstance(pipeline.get("current"), dict) else {}
    count = int(current.get("research_entities") or 0)
    research["organization"] = "public GitHub research universe (not live sales)"
    research["decision"] = "RESEARCH_UNIVERSE_NOT_LIVE_SALES"
    research["next_action"] = (
        f"do not treat {count} RESEARCH_REQUIRED GitHub entities as live sales next-actions"
    )
    research["live"] = False
    subjects[research["id"]] = research

    mailbox = _blank_row("swarm-mail-public-inboxes", "mailbox_manifest")
    box_rel = rel(paths["root"], paths["inboxes"])
    _touch(mailbox, "swarm_mail", box_rel)
    mailbox["organization"] = "Commons swarm mail public manifest"
    mailbox["decision"] = inboxes.get("transport", {}).get("state") if isinstance(inboxes.get("transport"), dict) else None
    mailbox["next_action"] = "NEEDS_OWNER_MAILBOX"
    mailbox["live"] = False
    subjects[mailbox["id"]] = mailbox

    apply_overlay_events(subjects, events)

    for row in subjects.values():
        if set(row) != ROW_KEYS:
            raise IndexError_(f"row {row.get('id')} keys drifted: {sorted(row)}")
        if row["cash_usd"] != 0:
            raise IndexError_(f"row {row['id']} claimed cash")
        if row["role"] == "seller_context" and row["live"]:
            raise IndexError_(f"seller contact {row['id']} marked live")
        if row["id"] in {"ava-example-test", "noah-example-test", "riley-quiet", "sam-example-test"}:
            if row["role"] != "seller_context" or row["live"]:
                raise IndexError_(f"seller fixture {row['id']} leaked into live sales")
    return subjects


def composed_at(paths: dict[str, Path], events: list[dict[str, Any]]) -> str:
    stamps = [
        read_object(paths["loop"]).get("generated_at"),
        read_object(paths["funnel"]).get("measured_at"),
        read_object(paths["pipeline"]).get("observed_at"),
        read_object(paths["inboxes"]).get("measured_at"),
        read_object(paths["candidates"]).get("generated_at"),
    ]
    stamps.extend(event.get("ts") for event in events)
    parsed = [parse_time(str(item)) for item in stamps if item]
    if not parsed:
        raise IndexError_("no source timestamps")
    return iso_z(max(parsed))


def build_index(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    loop = read_object(paths["loop"])
    pipeline = read_object(paths["pipeline"])
    events = load_events(paths)
    subjects = compose_subjects(paths)
    rows = sorted(
        subjects.values(),
        key=lambda row: (ROLE_ORDER.get(row["role"], 99), row["id"]),
    )
    live_rows = [row for row in rows if row["live"]]
    hot_rows = [row for row in rows if hot_class(row)]
    hold_rows = [row for row in rows if row.get("live") and row.get("decision") == HOLD_BUILD_DECISION]
    sent_dnr_rows = [row for row in rows if is_sent_dnr_row(row)]
    header = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_HEADER,
        "canonical_crm": CANONICAL_CRM,
        "public_projection_is_not_crm": True,
        "does_not_replace": list(DOES_NOT_REPLACE),
        "does_not_create": list(DOES_NOT_CREATE),
        "compose": dict(COMPOSE),
        "composed_at": composed_at(paths, events),
        "row_count": len(rows),
        "live_next_action_count": len(live_rows),
        "hot_next_action_count": len(hot_rows),
        "hold_build_action_count": len(hold_rows),
        "sent_awaiting_dnr_count": len(sent_dnr_rows),
        "cash_usd": 0,
    }
    truth = {
        "index_rows": len(rows),
        "live_next_actions": len(live_rows),
        "seller_context_rows": sum(1 for row in rows if row["role"] == "seller_context"),
        "external_prospects": sum(1 for row in rows if row["role"] == "external_prospect"),
        "inbound_contacts": sum(1 for row in rows if row["role"] == "inbound_contact"),
        "research_entities_not_live": int(
            (pipeline.get("current") or {}).get("research_entities") or 0
        ),
        "overlay_events": len(events),
        "hot_next_actions": len(hot_rows),
        "hold_build_actions": len(hold_rows),
        "sent_awaiting_dnr_actions": len(sent_dnr_rows),
        "calls_booked": int((loop.get("truth") or {}).get("calls_booked") or 0),
        "transport_actions": 0,
        "cash_usd": 0,
        "mailbox": (loop.get("truth") or {}).get("mailbox") or "NEEDS_OWNER_MAILBOX",
    }
    if truth["calls_booked"] != 0 or truth["cash_usd"] != 0:
        raise IndexError_("composer claimed bookings or cash")
    state = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_STATE,
        "canonical_crm": CANONICAL_CRM,
        "public_projection_is_not_crm": True,
        "does_not_replace": list(DOES_NOT_REPLACE),
        "does_not_create": list(DOES_NOT_CREATE),
        "compose": dict(COMPOSE),
        "composed_at": header["composed_at"],
        "index": INDEX_REL,
        "events": EVENTS_REL,
        "truth": truth,
        "named_subjects": {
            "composio": "external_prospect READY_TO_DRAFT from loop.json + candidates.json",
            "signoz": "external_prospect RESEARCH_REQUIRED from loop.json + candidates.json",
            "metaforms": "EXISTING_CRM_RECORD airtable:recWHbHxQoQfGhS0q; HOLD_DO_NOT_RESEND",
            "anythingllm-mintplex": "HOLD_DO_NOT_RESEND from receipts + loop.json",
            "city-of-billings-bid-1421": "OWNER_HOLD / DNR_OUTREACH / NOT_HOT; live owner path in #billings-1421-compliance; EXISTING_CRM_RECORD airtable:rec2mCS4ETa8FOvqN; agents do not send or contact Cheri",
            "pcl-ryan-ott": "HOLD_BUILD_AND_VERIFY demand pcl-scope-sla-routing-lims-01; runner on main; PRE-SALE TRANSPORT NONE",
            "canyon-wendy-mach": "HOLD_BUILD_AND_VERIFY demand canyon-multisite-regulated-intake-lims-01; runner on main; PRE-SALE TRANSPORT NONE",
            "ace-qat-erick-sharp": "HOLD_BUILD_AND_VERIFY demand ace-qat-thermal-rheology-capacity-lims-01; runner on main; PRE-SALE TRANSPORT NONE",
            "sgspsi-kyle-copeland": "HOLD_BUILD_AND_VERIFY demand sgspsi-high-throughput-thermal-rheology-lineage-lims-01; runner on main; PRE-SALE TRANSPORT NONE",
            "sharp-james-hamilton": "HOLD_BUILD_AND_VERIFY demand sharp-rtu-vial-isolator-lineage-lims-01; PRE-SALE TRANSPORT NONE",
            "csanalytical-brandon-zurawlow": "HOLD_BUILD_AND_VERIFY demand csanalytical-expansion-crossline-evidence-lims-01; runner on main; PRE-SALE TRANSPORT NONE",
            "rmb-robert-borash": "HOLD_BUILD_AND_VERIFY demand rmb-crosssite-courier-accession-lims-01; runner on main; PRE-SALE TRANSPORT NONE",
            "preinnewhof-steve-bylsma": "HOLD_BUILD_AND_VERIFY demand preinnewhof-pfas-fieldblank-gate-lims-01; runner on main; PRE-SALE TRANSPORT NONE",
            "luvak-dean-gaskill": "HOLD_BUILD_AND_VERIFY demand luvak-ssa-lab-analytics-cutover-lims-01; PRE-SALE TRANSPORT NONE",
            "mga-marshall-houston": "HOLD_BUILD_AND_VERIFY demand mga-alabama-materials-program-lims-01; PRE-SALE TRANSPORT NONE",
            "msp-integris": "EXISTING_CRM_RECORD airtable:recyxAWjUjrUY1Xln SENT/NO_REPLY/HARD_DO_NOT_RESEND",
            "mvmtc-craig-riviello": "HOLD_BUILD_AND_VERIFY demand mvmtc-aero-fastener-evidence-lims-01; PRE-SALE TRANSPORT NONE",
            "pace-amanda-yoakum": "HOLD_BUILD_AND_VERIFY demand pace-lebanon-microbial-volume-evidence-lims-01; PRE-SALE TRANSPORT NONE",
            "solstice-david-sewell": "HOLD_BUILD_AND_VERIFY demand solstice-batch-coa-transition-ledger-01; PRE-SALE TRANSPORT NONE",
            "rush-machinery-ryan-robbins": "HOLD_BUILD_AND_VERIFY demand rush-machinery-machine-service-evidence-ledger-01; PRE-SALE TRANSPORT NONE",
            "accreditedlabs-joe-moser": "HOLD_BUILD_AND_VERIFY demand accreditedlabs-multibrand-certificate-integration-gate-01; PRE-SALE TRANSPORT NONE",
            "packsize-eric-fisher": "HOLD_BUILD_AND_VERIFY demand packsize-iso9001-process-evidence-binder-01; PRE-SALE TRANSPORT NONE",
            "sanguine-gerald-lee": "HOLD_BUILD_AND_VERIFY demand sanguine-multispecimen-collection-window-validator-01; PRE-SALE TRANSPORT NONE",
            "fuse-jovie-tim-white": "EXISTING_CRM_RECORD airtable:recBHZw2VsWWmALcR SENT/AWAITING_REPLY/HARD_DO_NOT_RESEND",
            "fuse-avantstay-andrei-patseev": "EXISTING_CRM_RECORD airtable:recQL3RMLwizE6kgZ SENT/AWAITING_REPLY/HARD_DO_NOT_RESEND",
            "fuse-odderon-phi-charles": "EXISTING_CRM_RECORD airtable:recIo5cgbxL96aQSn SENT/AWAITING_REPLY/HARD_DO_NOT_RESEND",
            "fuse-immense-de-waal-immelman": "EXISTING_CRM_RECORD airtable:rec6SOShVG2fgZQi0 SENT/AWAITING_REPLY/HARD_DO_NOT_RESEND",
            "fuse-halo-ai-vito-strokov": "EXISTING_CRM_RECORD airtable:recIIo5M0lfUlYBXV BOUNCED/GROUP_ROUTE_REJECTED/HARD_DO_NOT_RESEND",
        },
        "contract": dict(CONTRACT),
    }
    blob = "".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in [header, *rows])
    _assert_no_pii_in_index_blob(blob)
    _assert_no_pii_in_index_blob(canonical_text(state))
    return {"header": header, "rows": rows, "state": state, "events": events, "blob": blob}


def write_index(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    built = build_index(paths)
    paths["index"].parent.mkdir(parents=True, exist_ok=True)
    paths["index"].write_text(built["blob"], encoding="utf-8")
    paths["state"].write_text(canonical_text(built["state"]), encoding="utf-8")
    if not paths["events"].exists():
        paths["events"].write_text("", encoding="utf-8")
    return built


def validate_index(paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    built = build_index(paths)
    actual_index = paths["index"].read_text(encoding="utf-8")
    if actual_index != built["blob"]:
        raise IndexError_("committed INDEX.jsonl differs from composed ledgers")
    actual_state = json.loads(paths["state"].read_text(encoding="utf-8"))
    if actual_state != built["state"]:
        raise IndexError_("committed state.json differs from composed ledgers")
    if built["state"]["truth"]["cash_usd"] != 0:
        raise IndexError_("cash_usd is not 0")
    for name in DOES_NOT_CREATE:
        if (paths["root"] / name.rstrip("/")).exists():
            raise IndexError_(f"remint root present: {name}")
    return built


def live_next_actions(paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    built = build_index(paths)
    return [row for row in built["rows"] if row["live"]]


def _source_excerpt(items: list[Any], key: str, value: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get(key) == value:
            return item
    return None


def show_subject(
    subject_id: str,
    paths: dict[str, Path] | None = None,
    *,
    sources: bool = False,
) -> dict[str, Any]:
    paths = paths or default_paths()
    built = build_index(paths)
    row = next((item for item in built["rows"] if item["id"] == subject_id), None)
    if row is None:
        raise IndexError_(
            f"unknown subject {subject_id!r}: composer opens existing ledger ids only and does not mint a contact book"
        )
    if not sources:
        compact = compact_row(row)
        compact["overlay_event_ids"] = list(row.get("overlay_event_ids") or [])
        compact["source_paths"] = list(row.get("source_paths") or [])
        _assert_no_pii_in_index_blob(json.dumps(compact, sort_keys=True, ensure_ascii=False))
        return compact
    ledgers: dict[str, Any] = {}
    loop = read_object(paths["loop"])
    if "website_people_email_book" in row["source_ledgers"]:
        if row["role"] == "seller_context":
            ledgers["website_people_email_book"] = _source_excerpt(
                loop.get("seller_contacts") or [], "contact_id", subject_id
            )
        else:
            ledgers["website_people_email_book"] = _source_excerpt(
                loop.get("prospects") or [], "prospect_id", subject_id
            )
            emails = [
                item
                for item in (loop.get("emails") or [])
                if isinstance(item, dict) and item.get("prospect_id") == subject_id
            ]
            bookings = [
                item
                for item in (loop.get("bookings") or [])
                if isinstance(item, dict) and item.get("prospect_id") == subject_id
            ]
            if emails:
                ledgers["website_people_email_book_emails"] = emails
            if bookings:
                ledgers["website_people_email_book_bookings"] = bookings
    if "smart_outreach" in row["source_ledgers"]:
        candidates = read_object(paths["candidates"])
        ledgers["smart_outreach"] = _source_excerpt(
            candidates.get("prospects") or [], "prospect_id", subject_id
        )
    if "reply_to_revenue" in row["source_ledgers"]:
        funnel = read_object(paths["funnel"])
        ledgers["reply_to_revenue"] = _source_excerpt(
            funnel.get("contacts") or [], "prospect_key", subject_id
        )
    if "outreach_receipts" in row["source_ledgers"]:
        ledgers["outreach_receipts"] = [
            {"path": item["path"], "do_not_resend": item["do_not_resend"]}
            for item in load_receipts(paths)
            if item["target_id"] == subject_id
        ]
    overlay = [event for event in built["events"] if event.get("subject_id") == subject_id]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "LM_GTM_INDEX_SHOW",
        "subject_id": subject_id,
        "index": row,
        "sources": ledgers,
        "overlay_events": overlay,
        "canonical_crm": CANONICAL_CRM,
        "cash_usd": 0,
    }


def append_event(
    *,
    subject_id: str,
    event_id: str,
    body: str,
    speaker: str = "UNSEATED",
    ts: str | None = None,
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    paths = paths or default_paths()
    if not EVENT_ID_RE.fullmatch(event_id):
        raise IndexError_(f"illegal overlay event id: {event_id}")
    text = body.strip()
    if not text:
        raise IndexError_("overlay event body is empty")
    built = build_index(paths)
    row = next((item for item in built["rows"] if item["id"] == subject_id), None)
    if row is None:
        raise IndexError_(
            f"unknown subject {subject_id!r}: composer does not mint a contact book"
        )
    if row["role"] not in {"external_prospect", "inbound_contact"}:
        raise IndexError_(
            f"{subject_id} is {row['role']}; overlay events cite live ledger subjects only"
        )
    existing_ids = {event["id"] for event in built["events"]}
    if event_id in existing_ids:
        raise IndexError_(f"overlay event remint refused: {event_id}")
    stamp = ts or iso_z(dt.datetime.now(dt.timezone.utc))
    parse_time(stamp)
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_EVENT,
        "id": event_id,
        "subject_id": subject_id,
        "ts": stamp,
        "from": speaker or "UNSEATED",
        "body": text,
        "type": NOTE_TYPE,
        "cash_usd": 0,
        "transport": "NONE",
    }
    events = list(built["events"])
    events.append(event)
    write_jsonl(paths["events"], events)
    written = write_index(paths)
    return {"event": event, "index": written}


def _occupancy_event_id(kind: str, subject_id: str, stamp: str) -> str:
    compact = stamp.replace("-", "").replace(":", "")
    slug = f"lm-gtm-{kind}-{subject_id}-{compact}"
    if len(slug) > 80:
        slug = f"lm-gtm-{kind}-{compact}"
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", slug)
    if not EVENT_ID_RE.fullmatch(slug):
        raise IndexError_(f"illegal overlay event id: {slug}")
    return slug


def _live_row(subject_id: str, paths: dict[str, Path]) -> dict[str, Any]:
    built = build_index(paths)
    row = next((item for item in built["rows"] if item["id"] == subject_id), None)
    if row is None:
        raise IndexError_(
            f"unknown subject {subject_id!r}: composer does not mint a contact book"
        )
    if row["role"] not in LIVE_ROLES:
        raise IndexError_(
            f"{subject_id} is {row['role']}; occupancy cites live ledger subjects only"
        )
    return row


def claim_subject(
    *,
    subject_id: str,
    owner: str,
    steal: bool = False,
    ts: str | None = None,
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    paths = paths or default_paths()
    name = (owner or "").strip() or "UNSEATED"
    if name == "UNSEATED":
        raise IndexError_("occupancy claim needs a named owner; UNSEATED is empty occupancy")
    row = _live_row(subject_id, paths)
    current = row.get("owner") or "UNSEATED"
    if current == name and not steal:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "LM_GTM_OCCUPANCY",
            "status": "already_occupied",
            "subject_id": subject_id,
            "owner": name,
            "steal": False,
            "cash_usd": 0,
            "transport": "NONE",
        }
    if current not in {"UNSEATED", name} and not steal:
        raise IndexError_(
            f"{subject_id} occupied by {current}; second occupancy fails closed without --steal"
        )
    stamp = ts or iso_z(dt.datetime.now(dt.timezone.utc))
    parse_time(stamp)
    etype = "STEAL" if steal and current not in {"UNSEATED", name} else "CLAIM"
    event_id = _occupancy_event_id(etype.lower(), subject_id, stamp)
    existing_ids = {event["id"] for event in load_events(paths)}
    if event_id in existing_ids:
        raise IndexError_(f"overlay event remint refused: {event_id}")
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_EVENT,
        "id": event_id,
        "subject_id": subject_id,
        "type": etype,
        "ts": stamp,
        "from": name,
        "owner": name,
        "body": f"{etype} occupancy on {subject_id}",
        "cash_usd": 0,
        "transport": "NONE",
    }
    events = load_events(paths)
    events.append(event)
    write_jsonl(paths["events"], events)
    written = write_index(paths)
    return {"event": event, "index": written, "status": "occupied", "owner": name}


def release_subject(
    *,
    subject_id: str,
    owner: str,
    ts: str | None = None,
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    paths = paths or default_paths()
    name = (owner or "").strip() or "UNSEATED"
    row = _live_row(subject_id, paths)
    current = row.get("owner") or "UNSEATED"
    if current == "UNSEATED":
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "LM_GTM_OCCUPANCY",
            "status": "already_released",
            "subject_id": subject_id,
            "owner": "UNSEATED",
            "cash_usd": 0,
            "transport": "NONE",
        }
    if name == "UNSEATED" or current != name:
        raise IndexError_(
            f"{subject_id} occupied by {current}; release fails closed for {name}"
        )
    stamp = ts or iso_z(dt.datetime.now(dt.timezone.utc))
    parse_time(stamp)
    event_id = _occupancy_event_id("release", subject_id, stamp)
    existing_ids = {event["id"] for event in load_events(paths)}
    if event_id in existing_ids:
        raise IndexError_(f"overlay event remint refused: {event_id}")
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_EVENT,
        "id": event_id,
        "subject_id": subject_id,
        "type": "RELEASE",
        "ts": stamp,
        "from": name,
        "owner": name,
        "body": f"RELEASE occupancy on {subject_id}",
        "cash_usd": 0,
        "transport": "NONE",
    }
    events = load_events(paths)
    events.append(event)
    write_jsonl(paths["events"], events)
    written = write_index(paths)
    return {"event": event, "index": written, "status": "released", "owner": "UNSEATED"}


def assert_sales_owner(
    *,
    subject_id: str,
    owner: str,
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Exit-0 helper: live occupant after compose must equal YOU.

    UNSEATED or a different occupant raises UnclaimedSales (CLI exit 4).
    Unknown / non-live subjects stay IndexError_ (CLI exit 1).
    """
    paths = paths or default_paths()
    name = (owner or "").strip() or "UNSEATED"
    row = _live_row(subject_id, paths)
    current = row.get("owner") or "UNSEATED"
    if current == "UNSEATED" or current != name:
        raise UnclaimedSales(
            f"unclaimed sales {subject_id}: live owner is {current}, --owner is {name}; "
            "sales/draft/outreach illegal without matching occupancy (exit 4)"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "LM_GTM_SALES_OCCUPANCY",
        "status": "occupied",
        "subject_id": subject_id,
        "owner": name,
        "cash_usd": 0,
        "transport": "NONE",
    }


def occupancy_subject(args: argparse.Namespace) -> str:
    positional = str(getattr(args, "subject_pos", "") or "").strip()
    flagged = str(getattr(args, "subject_flag", "") or "").strip()
    if positional and flagged and positional != flagged:
        raise IndexError_("occupancy command got conflicting positional and --subject values")
    subject = positional or flagged
    if not subject:
        raise IndexError_("occupancy command needs a subject (positional or --subject)")
    return subject


def _add_occupancy_args(parser: argparse.ArgumentParser, *, steal: bool) -> None:
    parser.add_argument(
        "subject_pos",
        nargs="?",
        default="",
        metavar="subject",
        help="live subject id; same as --subject",
    )
    parser.add_argument("--subject", dest="subject_flag", default="", help="live subject id")
    parser.add_argument("--owner", required=True, help="named occupant; required for a real claim or release")
    if steal:
        parser.add_argument("--steal", action="store_true")
    parser.add_argument("--ts")


def read_committed_composed_at(paths: dict[str, Path] | None = None) -> str:
    """Read the saved INDEX timestamp, or state.json when INDEX is absent."""
    paths = paths or default_paths()
    rows = load_jsonl(paths["index"])
    if rows:
        if rows[0].get("kind") != KIND_HEADER:
            raise IndexError_("INDEX first row must be its header")
        stamp = rows[0].get("composed_at")
    elif paths["state"].exists():
        stamp = read_object(paths["state"]).get("composed_at")
    else:
        raise IndexError_("INDEX/state missing composed_at")
    if not isinstance(stamp, str) or not stamp.strip():
        raise IndexError_("INDEX/state missing composed_at")
    return stamp.strip()


def composed_at_freshness(
    paths: dict[str, Path] | None = None,
    *,
    now: dt.datetime | None = None,
    composed_at_value: str | None = None,
) -> dict[str, Any]:
    """Describe timestamp age; this does not grant or restrict any operation."""
    composed = (
        read_committed_composed_at(paths)
        if composed_at_value is None else composed_at_value
    )
    if not isinstance(composed, str) or not composed.strip():
        raise IndexError_("composed_at must be a nonempty timestamp")
    stamped = parse_time(composed)
    instant = now if now is not None else dt.datetime.now(dt.timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise IndexError_("as_of must include a timezone")
    age = instant - stamped
    if age < dt.timedelta(0):
        raise IndexError_("composed_at is later than as_of; freshness is unknown")
    stale = age > STALE_AFTER
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "LM_GTM_COMPOSED_AT_FRESHNESS",
        "status": "STALE" if stale else "FRESH",
        "composed_at": composed,
        "as_of": iso_z(instant),
        "age_hours": round(age.total_seconds() / 3600.0, 6),
        "threshold_hours": STALE_AFTER.total_seconds() / 3600.0,
        "canonical_crm": CANONICAL_CRM,
        "cash_usd": 0,
    }
    if stale:
        payload["stale_warning"] = STALE_WARNING
    _assert_no_pii_in_index_blob(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("write-index")
    sub.add_parser("snapshot")
    sub.add_parser("next")
    sub.add_parser("brief")
    freshness = sub.add_parser("freshness", help="describe saved INDEX age")
    freshness.add_argument("--as-of", help="timezone-aware time; defaults to current UTC")
    sub.add_parser("sent")
    hot = sub.add_parser("hot")
    hot.add_argument("--brief", action="store_true")
    hold = sub.add_parser("hold")
    hold.add_argument("--brief", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("subject")
    show.add_argument("--sources", action="store_true")
    append = sub.add_parser("append-event")
    append.add_argument("--subject", required=True)
    append.add_argument("--id", dest="event_id", required=True)
    append.add_argument("--body", required=True)
    append.add_argument("--from", dest="speaker", default="UNSEATED")
    append.add_argument("--ts")
    occupy = sub.add_parser("claim")
    _add_occupancy_args(occupy, steal=True)
    release = sub.add_parser("release")
    _add_occupancy_args(release, steal=False)
    need = sub.add_parser("require-claim")
    _add_occupancy_args(need, steal=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--send" in argv or argv[:1] == ["send"]:
        sys.stderr.write(
            "REFUSED live send: this composer never transports mail. "
            "Use Swarm Mail after measured provisioning; overlay events stay local.\n"
        )
        return 3
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            built = validate_index()
            truth = built["state"]["truth"]
            print(
                "VALID "
                f"{truth['live_next_actions']} live-next "
                f"{truth.get('hot_next_actions', 0)} hot "
                f"{truth['external_prospects']} prospects "
                f"{truth['inbound_contacts']} inbound "
                f"{truth['seller_context_rows']} seller-context "
                f"{truth['overlay_events']} overlay-events "
                f"USD {truth['cash_usd']} cash"
            )
            return 0
        if args.command in {"write-index", "snapshot"}:
            built = write_index()
            print(canonical_text(built["state"]), end="")
            return 0
        if args.command == "next":
            rows = live_next_actions()
            sys.stdout.write(
                "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
            )
            return 0
        if args.command == "brief":
            built = build_index()
            sys.stdout.write(emit_jsonl([brief_header(built=built), *brief_hot_rows()]))
            return 0
        if args.command == "freshness":
            result = composed_at_freshness(now=parse_time(args.as_of) if args.as_of else None)
            print(canonical_text(result), end="")
            return 0 if result["status"] == "FRESH" else 2
        if args.command == "sent":
            sys.stdout.write(emit_jsonl(compact_sent_rows()))
            return 0
        if args.command == "hot":
            if args.brief:
                sys.stdout.write(emit_jsonl(brief_hot_rows()))
            else:
                rows = hot_next_actions()
                sys.stdout.write(
                    "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
                )
            return 0
        if args.command == "hold":
            if args.brief:
                sys.stdout.write(emit_jsonl(compact_hold_rows()))
            else:
                rows = hold_build_next_actions()
                sys.stdout.write(
                    "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)
                )
            return 0
        if args.command == "show":
            print(canonical_text(show_subject(args.subject, sources=args.sources)), end="")
            return 0
        if args.command == "append-event":
            result = append_event(
                subject_id=args.subject,
                event_id=args.event_id,
                body=args.body,
                speaker=args.speaker,
                ts=args.ts,
            )
            print(canonical_text(result["event"]), end="")
            return 0
        if args.command == "claim":
            result = claim_subject(
                subject_id=occupancy_subject(args),
                owner=args.owner,
                steal=args.steal,
                ts=args.ts,
            )
            print(canonical_text(result.get("event") or result), end="")
            return 0
        if args.command == "release":
            result = release_subject(
                subject_id=occupancy_subject(args),
                owner=args.owner,
                ts=args.ts,
            )
            print(canonical_text(result.get("event") or result), end="")
            return 0
        if args.command == "require-claim":
            result = assert_sales_owner(
                subject_id=occupancy_subject(args),
                owner=args.owner,
            )
            print(canonical_text(result), end="")
            return 0
        raise IndexError_(f"unknown command {args.command}")
    except SendError as error:
        print(str(error), file=sys.stderr)
        return 3
    except UnclaimedSales as error:
        print(str(error), file=sys.stderr)
        return 4
    except IndexError_ as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
