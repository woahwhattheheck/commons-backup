"""Deterministic mail projection over selected WorkstreamStore metadata.

No mailbox reads/writes, body parsing, payment inference, or persistence occurs
here. ``waiting_on`` describes the last observed conversation turn, not a claim
that a message requires a reply. Missing coverage/freshness keeps it unknown.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from email.utils import getaddresses

UTC = timezone.utc
ERRORS = {"error", "failed", "offline", "unavailable", "blocked"}
MAX_MESSAGES = 20
MAX_REFS = 20
MAX_SOURCE_IDS = 20
MAX_NOTES = 5
MAX_ID = 512
MAX_TEXT = 500
MAX_ACTION = 2000
MAX_URL = 2048
CONNECTOR_ADDRESS = re.compile(r'([^@<>]+?)\s+([^@\s<>()\[\]\\,;:"]+@[^@\s<>()\[\]\\,;:"]+)')


def _obj(value):
    return value if isinstance(value, dict) else {}


def _text(*values):
    return next((value for value in values if isinstance(value, str) and value.strip()), None)


def _display(value, limit=MAX_TEXT):
    return value[:limit] if isinstance(value, str) else None


def _identifier(value):
    # Do not return a truncated provider identifier that looks actionable.
    return value if isinstance(value, str) and 0 < len(value) <= MAX_ID else None


def _list(value):
    return value if isinstance(value, list) else []


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _time(value):
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, OverflowError, TypeError):
        return None


def _iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def _rank(value):
    parsed = _time(value)
    return parsed.timestamp() if parsed else float("-inf")


def _addresses(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return set()
    headers = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        # Gmail connector metadata renders one mailbox as "Display Name addr".
        # Select that address before parsing; leave ordinary headers,
        # address lists and quoted local parts to the standard parser.
        match = CONNECTOR_ADDRESS.fullmatch(entry.strip())
        headers.append(match.group(2) if match else entry)
    return {address.lower() for _, address in getaddresses(headers) if "@" in address}


def _account(item, source):
    refs, meta, scope = _obj(item.get("refs")), _obj(item.get("metadata")), _obj(source.get("scope"))
    value = _text(refs.get("mailbox"), refs.get("account_id"), refs.get("account"),
                  meta.get("mailbox"), meta.get("account_id"), scope.get("mailbox"),
                  scope.get("account_id"), scope.get("account"))
    if not value:
        return None
    value = value.strip()
    return value.lower() if "@" in value else value


def _source(source, now):
    good = _time(source.get("last_good_observed_at"))
    success = _time(source.get("last_success_at"))
    threshold = source.get("stale_after_seconds", 900)
    if good is None or good > now:
        stale = None
    elif threshold is None:
        stale = False
    elif _finite(threshold) and threshold >= 0:
        stale = (now - good).total_seconds() > threshold
    else:
        stale = None
    if source.get("data_stale") is True:
        stale = True
    failed = bool(source.get("error")) or str(source.get("status", "")).lower() in ERRORS
    retained = bool(source.get("retained_last_good"))
    coverage = _obj(source.get("last_good_coverage")) or _obj(source.get("coverage"))
    complete = coverage.get("complete") if type(coverage.get("complete")) is bool else None
    if coverage.get("pagination_remaining") not in (None, False, 0):
        complete = False
    notes = [note for note in _list(coverage.get("notes")) if isinstance(note, str)]
    pagination = coverage.get("pagination_remaining")
    if not (pagination is None or type(pagination) is bool or type(pagination) is int and 0 <= pagination <= 1_000_000_000):
        pagination = None
    return {"id": _identifier(source.get("id")), "provider": _display(source.get("provider"), 80),
            "label": _display(source.get("label")), "sync_mode": _display(source.get("sync_mode"), 80),
            "account": _identifier(_account({}, source)), "last_attempt_at": _iso(_time(source.get("last_attempt_at"))),
            "last_success_at": _iso(success), "last_good_observed_at": _iso(good),
            "status": _display(source.get("status"), 80), "source_error": failed,
            "stale": stale, "age_seconds": max(0, (now - good).total_seconds()) if good and good <= now else None,
            "retained_last_good": retained,
            "coverage": {"complete": complete, "pagination_remaining": pagination,
                         "notes": [_display(note) for note in notes[:MAX_NOTES]],
                         "notes_omitted": max(0, len(notes) - MAX_NOTES),
                         "note_texts_truncated": sum(len(note) > MAX_TEXT for note in notes[:MAX_NOTES])},
            "current": good is not None and stale is False and not failed and not retained
                       and success is not None and success <= now}


def _direction(item, account, labels):
    meta = _obj(item.get("metadata"))
    status = str(item.get("status", "")).lower()
    if "DRAFT" in labels or status == "draft":
        return "draft"
    sender = _addresses(meta.get("from_", meta.get("from")))
    recipients = _addresses(meta.get("to")) | _addresses(meta.get("cc"))
    sent = "SENT" in labels or status == "sent" or meta.get("direction") == "outbound"
    if sent:
        if account and recipients == {account}:
            return "self"
        if "INBOX" in labels and not recipients:
            return "unknown"
        return "outbound"
    if account and account in sender:
        return "self" if recipients == {account} else "unknown"
    if meta.get("direction") == "inbound" or status in {"received", "unread"} or "INBOX" in labels:
        return "inbound"
    if account and account in recipients and sender and account not in sender:
        return "inbound"
    return "unknown"


def _message(item, source, state):
    refs, meta = _obj(item.get("refs")), _obj(item.get("metadata"))
    account = _account(item, source)
    provider = (_text(item.get("provider"), source.get("provider")) or "unknown").lower()
    source_id, item_id = str(item.get("source_id", "")), str(item.get("id", ""))
    message_id = _text(refs.get("gmail_message_id"), refs.get("message_id"), meta.get("message_id"), item.get("provider_id"))
    thread_id = _text(refs.get("gmail_thread_id"), refs.get("thread_id"), meta.get("thread_id"))
    labels_raw = item.get("labels", meta.get("labels"))
    labels = {entry.upper() for entry in labels_raw if isinstance(entry, str)} if isinstance(labels_raw, list) else set()
    unread = "UNREAD" in labels if isinstance(labels_raw, list) else (
        meta.get("unread") if type(meta.get("unread")) is bool else True if item.get("status") == "unread" else None)
    at = next((parsed for value in (meta.get("email_ts"), meta.get("sent_at"), meta.get("received_at"),
               item.get("activity_observed_at"), item.get("updated_at")) if (parsed := _time(value))), None)
    account_key = account if account else ("unknown-account", source_id)
    key = (provider, account_key, message_id or ("unknown-message", source_id, item_id))
    seen = _time(item.get("last_seen_at"))
    good = _time(source.get("last_good_observed_at"))
    observed = min(seen, good) if seen and good else seen or good
    member = seen is not None and seen == _time(source.get("last_success_at"))
    return {"key": key, "account": account, "account_key": account_key, "provider": provider,
            "message_id": message_id, "thread_id": thread_id, "source_id": source_id,
            "item_id": item_id, "at": _iso(at), "direction": _direction(item, account, labels),
            "unread": unread, "last_seen_at": _iso(seen), "observation_at": _iso(observed),
            "current": bool(state["current"] and member),
            "complete": state["coverage"]["complete"] is True,
            "conflict": False, "record": item, "records": [item]}


def _reduce(observations):
    """Reduce all copies together; synthetic conflict values never become votes."""
    fields = ("thread_id", "at", "direction", "unread")
    newest = max(_rank(row["observation_at"]) for row in observations)
    peers = [row for row in observations if _rank(row["observation_at"]) == newest]
    selected = max(peers, key=lambda row: (row["source_id"], row["item_id"]))
    result = dict(selected)
    conflicts = [field for field in fields if len({row[field] for row in peers}) > 1]
    for field in conflicts:
        result[field] = "unknown" if field == "direction" else None
    result["conflict"] = bool(conflicts)
    result["conflict_fields"] = conflicts
    equivalent = [row for row in observations if all(row[field] == result[field] for field in fields)]
    # Older equivalent copies can supply fresh complete evidence. Provenance
    # that is stale/partial does not negate an equivalent successful read.
    evidence = peers if conflicts else equivalent
    result["current"] = any(row["current"] for row in evidence)
    result["complete"] = any(row["complete"] for row in evidence)
    result["current_complete"] = any(row["current"] and row["complete"] for row in evidence)
    if equivalent:
        support = max(equivalent, key=lambda row: (row["current"] and row["complete"], row["current"],
                      _rank(row["observation_at"]), row["source_id"], row["item_id"]))
        for field in ("source_id", "item_id", "last_seen_at", "record"):
            result[field] = support[field]
    result["records"] = [row["record"] for row in observations]
    return result


def _priority(value):
    try:
        number = float(value) if not isinstance(value, bool) else float("inf")
        return number if math.isfinite(number) and number >= 0 else float("inf")
    except (TypeError, ValueError, OverflowError):
        return float("inf")


def _directive(records, field):
    candidates = [row for row in records if field in _obj(row.get("owner_work"))]
    if not candidates:
        return False, None, None
    row = max(candidates, key=lambda row: (_rank(_obj(row.get("owner_work")).get("updated_at")),
              str(row.get("source_id", "")), str(row.get("id", ""))))
    return True, row["owner_work"][field], {"source_id": _identifier(row.get("source_id")), "item_id": _identifier(row.get("id"))}


def project(work, now=None):
    """Return thread metadata without mutating the input or reading providers.

    Input is WorkstreamStore.state(). Message identity is scoped by provider and
    account; missing identity is isolated by source/item, never guessed from a
    subject. Owner directives survive cross-source message deduplication.
    """
    work = _obj(work)
    stamp = datetime.now(UTC) if now is None else _time(now)
    if stamp is None:
        raise ValueError("now must be a timezone-aware ISO timestamp or datetime")
    sources = {str(row["id"]): row for row in _list(work.get("sources")) if isinstance(row, dict) and "id" in row}
    email = [row for row in _list(work.get("items")) if isinstance(row, dict) and str(row.get("kind", "")).lower() == "email"]
    mail_source_ids = {str(row.get("source_id", "")) for row in email}
    mail_source_ids.update(key for key, row in sources.items() if str(row.get("provider", "")).lower() in {"gmail", "email", "mail"})
    source_states = {key: _source(sources.get(key, {"id": key}), stamp) for key in sorted(mail_source_ids)}
    observations = {}
    for item in email:
        source_id = str(item.get("source_id", ""))
        candidate = _message(item, sources.get(source_id, {}), source_states[source_id])
        observations.setdefault(candidate["key"], []).append(candidate)
    messages = {key: _reduce(rows) for key, rows in observations.items()}
    groups = {}
    for message in messages.values():
        thread_key = message["thread_id"] or ("unknown-thread", message["key"])
        key = (message["provider"], message["account_key"], thread_key)
        groups.setdefault(key, []).append(message)
    threads = []
    for key, rows in groups.items():
        rows.sort(key=lambda row: (_rank(row["at"]), row["message_id"] or "", row["source_id"], row["item_id"]))
        latest = rows[-1]
        records = [record for row in rows for record in row["records"]]
        records.sort(key=lambda row: (_rank(row.get("activity_observed_at") or row.get("updated_at")), _rank(row.get("last_seen_at")),
                     str(row.get("source_id", "")), str(row.get("id", ""))))
        record = latest["record"]
        source_ids = sorted({str(row.get("source_id", "")) for row in records})
        complete = all(row["complete"] for row in rows)
        current = all(row["current"] for row in rows)
        current_complete = all(row["current_complete"] for row in rows)
        dated = [row for row in rows if row["at"] and row["direction"] != "draft"]
        latest_at = max((_rank(row["at"]) for row in dated), default=None)
        directions = {row["direction"] for row in dated if _rank(row["at"]) == latest_at}
        observed = "waiting_on_us" if directions == {"inbound"} else "waiting_on_them" if directions == {"outbound"} else "unknown"
        conflict = any(row["conflict"] for row in rows)
        if any((not row["at"] or _rank(row["at"]) > stamp.timestamp()) and row["direction"] != "draft" for row in rows) or conflict:
            observed = "unknown"
        identity_complete = bool(_identifier(latest["account"]) and _identifier(latest["thread_id"])
                                 and all(_identifier(row["message_id"]) for row in rows))
        waiting = observed if current_complete and identity_complete else "unknown"
        reasons = ([] if current else ["stale_or_retained_source"]) + ([] if complete else ["incomplete_source_coverage"])
        if not identity_complete:
            reasons.append("missing_provider_identity")
        if observed == "unknown":
            reasons.append("ambiguous_or_missing_message_direction_time")
        if conflict:
            reasons.append("conflicting_duplicate_observation")
        if current and complete and not current_complete:
            reasons.append("no_current_complete_observation")
        unread = True if any(row["unread"] is True for row in rows) else False if all(row["unread"] is False for row in rows) else None
        found, next_action, directive_ref = _directive(records, "next_action")
        if not found:
            next_action = record.get("next_action")
        has_priority, priority, _ = _directive(records, "priority")
        if not has_priority:
            priority = record.get("priority")
        _, job, _ = _directive(records, "job")
        has_owner, assigned_owner, assigned_ref = _directive(records, "owner")
        assigned_source = "owner_work.owner" if has_owner else None
        if not has_owner and isinstance(job, dict) and "owner" in job:
            assigned_owner = job["owner"]
            assigned_source = "owner_work.job.owner"
            _, _, assigned_ref = _directive(records, "job")
        due_records = [row["record"] for row in rows if "due_at" in row["record"]]
        due_value = due_records[-1].get("due_at") if due_records else None
        due_source = "item.due_at" if due_records else None
        if isinstance(job, dict) and "due_at" in job:
            due_value, due_source = job["due_at"], "owner_work.job.due_at"
        due = _time(due_value)
        public_messages = [{**{field: _identifier(row[field]) for field in ("message_id", "source_id", "item_id")},
                            **{field: row[field] for field in ("at", "direction", "unread", "last_seen_at", "conflict")},
                            "conflict_fields": row["conflict_fields"],
                            "identifiers_omitted": [field for field in ("message_id", "source_id", "item_id")
                                                    if row[field] is not None and _identifier(row[field]) is None]}
                           for row in rows[-MAX_MESSAGES:]]
        ref_keys = sorted({(str(row.get("source_id", "")), str(row.get("id", ""))) for row in records})
        public_refs = [{"source_id": _identifier(source_id), "item_id": _identifier(item_id)}
                       for source_id, item_id in ref_keys[:MAX_REFS]]
        display_fields = {"title": (record.get("title"), MAX_TEXT), "url": (record.get("url"), MAX_URL),
                          "source_owner": (record.get("owner"), MAX_TEXT),
                          "correspondent": (_obj(record.get("metadata")).get("from_") or record.get("owner"), MAX_TEXT),
                          "assigned_owner": (assigned_owner, MAX_TEXT), "next_action": (next_action, MAX_ACTION)}
        clipped = {field: _display(value, limit) for field, (value, limit) in display_fields.items()}
        threads.append({"id": "mail:" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:24],
            "provider": _display(latest["provider"], 80), "account": _identifier(latest["account"]), "thread_id": _identifier(latest["thread_id"]),
            "identity_complete": identity_complete, **clipped,
            "message_count": len(rows), "messages": public_messages, "messages_omitted": max(0, len(rows) - MAX_MESSAGES),
            "source_ids": [_identifier(value) for value in source_ids[:MAX_SOURCE_IDS]],
            "source_ids_omitted": max(0, len(source_ids) - MAX_SOURCE_IDS),
            "last_activity_at": _iso(datetime.fromtimestamp(latest_at, UTC)) if latest_at is not None else None,
            "last_inbound_at": max((row["at"] for row in rows if row["direction"] == "inbound" and row["at"]), key=_rank, default=None),
            "last_outbound_at": max((row["at"] for row in rows if row["direction"] == "outbound" and row["at"]), key=_rank, default=None),
            "observed_waiting_on": observed, "waiting_on": waiting, "waiting_reasons": reasons,
            "unread": unread, "owner": clipped["assigned_owner"], "owner_source": assigned_source,
            "assigned_owner_source": assigned_source, "assigned_owner_ref": assigned_ref,
            "directive_ref": directive_ref, "priority": _display(priority, 80) if isinstance(priority, str) else priority
                if _finite(priority) else None,
            "_priority_sort": _priority(priority),
            "prepared_job": {"id": _identifier(job.get("id")), "status": _display(job.get("status"), 80),
                             "dispatch_status": _display(job.get("dispatch_status"), 80),
                             "created_at": _iso(_time(job.get("created_at")))} if isinstance(job, dict) else None,
            "due_at": _iso(due), "due_source": due_source, "overdue": due < stamp if due else None,
            "current_observation": current, "coverage_complete": complete, "current_complete_observation": current_complete,
            "record_refs": public_refs, "record_refs_omitted": max(0, len(ref_keys) - MAX_REFS),
            "truncated_fields": sorted(field for field, (value, limit) in display_fields.items()
                                       if isinstance(value, str) and len(value) > limit)
                                + (["priority"] if isinstance(priority, str) and len(priority) > 80 else []),
            "identifiers_omitted": [field for field in ("account", "thread_id") if latest[field] is not None and _identifier(latest[field]) is None]
                                   + (["prepared_job.id"] if isinstance(job, dict) and job.get("id") is not None and _identifier(job["id"]) is None else [])})
    threads.sort(key=lambda row: (row["_priority_sort"], not bool(row["overdue"]),
                                 -_rank(row["last_activity_at"]), row["id"]))
    for row in threads:
        row.pop("_priority_sort")
    states = list(source_states.values())
    return {"ok": True, "observed_at": _iso(stamp), "threads": threads, "sources": states,
            "counts": {"threads": len(threads), "messages": len(messages), "email_records": len(email),
                       "duplicate_records": len(email) - len(messages), "unread_threads": sum(row["unread"] is True for row in threads),
                       **{state: sum(row["waiting_on"] == state for row in threads) for state in ("waiting_on_us", "waiting_on_them", "unknown")}},
            "coverage": {"complete": bool(states) and all(row["coverage"]["complete"] is True for row in states),
                         "current": bool(states) and all(row["current"] for row in states)},
            "notes": ["Waiting state is last-observed direction, not an inferred reply obligation.",
                      "Assigned owner is explicit owner_work metadata; source_owner/correspondent is not assignment.",
                      "Mail prose never establishes payment; no mailbox operations are performed."]}

