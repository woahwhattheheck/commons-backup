#!/usr/bin/env python3
"""Consume existing Gmail connector reads without storing private mail.

The caller supplies {"messages": [Gmail message objects],
"buyer_message_ids": [the IDs the caller identifies as buyer replies]}.
Message objects use the installed Gmail connector's id, thread_id,
internal_date and label_ids fields; Gmail REST camelCase is also accepted.
Include the existing SENT messages referenced by the subject's canonical
events so that replies can be associated with that subject's conversations.

This is an in-memory projection for relationship handoff. It neither fetches
mail nor changes CRM, contact holds, ledgers or the supplied observations.
Bodies, headers, addresses and attachments never enter the returned packet.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any


_PROVIDER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_GMAIL_REF = re.compile(r"^gmail:([A-Za-z0-9_-]{1,128})$")


def _provider_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _PROVIDER_ID.fullmatch(value):
        raise ValueError(f"mailbox observations require a Gmail {field}")
    return value


def _message(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("mailbox observations messages must be objects")
    # Accept the structured result of a single installed connector read.
    source = raw.get("result", raw)
    if not isinstance(source, dict):
        raise ValueError("mailbox observation result must be an object")
    mid = _provider_id(source.get("id"), "message id")
    thread_id = _provider_id(
        source.get("thread_id", source.get("threadId")), "thread id"
    )
    raw_stamp = source.get("internal_date", source.get("internalDate"))
    if isinstance(raw_stamp, bool) or not isinstance(raw_stamp, (str, int)):
        raise ValueError("mailbox observations require internal_date milliseconds")
    try:
        millis = int(raw_stamp)
        # Keep provider milliseconds exact; a float loses precision near
        # the supported datetime range boundaries.
        stamp = (dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
                 + dt.timedelta(milliseconds=millis))
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError("mailbox observation has invalid internal_date") from error
    labels = source.get("label_ids", source.get("labelIds"))
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValueError("mailbox observations require label_ids from the provider")
    return {
        "id": mid,
        "thread_id": thread_id,
        "milliseconds": millis,
        "ts": stamp.isoformat().replace("+00:00", "Z"),
        "labels": frozenset(labels),
    }


def observe_buyer_replies(
    subject_id: str,
    snapshot: dict[str, Any],
    subject_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project caller-identified buyer replies against existing SENT pointers.

    Provider message IDs make repeated snapshots idempotent. A reply is an
    observation of mail, not an inference of consent, acceptance or payment.
    The result describes only the supplied snapshot, not the entire mailbox.
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("messages"), list):
        raise ValueError("mailbox observations require a messages array")
    buyer_ids = snapshot.get("buyer_message_ids")
    if not isinstance(buyer_ids, list):
        raise ValueError("mailbox observations require buyer_message_ids from the caller")
    buyer_ids = set(_provider_id(item, "buyer message id") for item in buyer_ids)
    messages: dict[str, dict[str, Any]] = {}
    for raw in snapshot["messages"]:
        message = _message(raw)
        previous = messages.get(message["id"])
        if previous is not None:
            # Labels may change between reads. Keep immutable identity/time
            # consistent and union labels so a sent/draft copy stays excluded.
            if any(previous[k] != message[k] for k in ("thread_id", "milliseconds")):
                raise ValueError("duplicate Gmail message has conflicting identity metadata")
            message["labels"] |= previous["labels"]
        messages[message["id"]] = message
    if buyer_ids - messages.keys():
        raise ValueError("include message records for every supplied buyer_message_id")

    anchor_ids: set[str] = set()
    for event in subject_events:
        if event.get("subject_id") != subject_id or event.get("type") != "SENT_AWAITING_REPLY":
            continue
        for pointer in event.get("source_paths") or []:
            match = _GMAIL_REF.fullmatch(pointer) if isinstance(pointer, str) else None
            if match:
                anchor_ids.add(match.group(1))

    outbound = [
        messages[mid] for mid in sorted(anchor_ids & messages.keys())
        if "SENT" in messages[mid]["labels"] and "DRAFT" not in messages[mid]["labels"]
    ]
    first_sent: dict[str, int] = {}
    for message in outbound:
        thread_id = message["thread_id"]
        first_sent[thread_id] = min(
            first_sent.get(thread_id, message["milliseconds"]), message["milliseconds"]
        )
    replies = [
        message for mid, message in messages.items()
        if mid in buyer_ids
        and not message["labels"].intersection({"SENT", "DRAFT"})
        and message["thread_id"] in first_sent
        and message["milliseconds"] >= first_sent[message["thread_id"]]
    ]
    replies.sort(key=lambda item: (item["milliseconds"], item["id"]))
    reply_ids = {message["id"] for message in replies}
    status = (
        "BUYER_REPLY_OBSERVED" if replies else
        "OUTBOUND_CONTEXT_MISSING" if not outbound else
        "NO_BUYER_REPLY_IN_SNAPSHOT"
    )
    return {
        "kind": "LM_GTM_MAILBOX_OBSERVATIONS",
        "subject_id": subject_id,
        "status": status,
        "mode": "PROVIDER_SNAPSHOT",
        "provider": "gmail",
        "buyer_classification": "CALLER_SUPPLIED",
        "outbound_message_ids": [message["id"] for message in outbound],
        "inbound_buyer_message_ids": [message["id"] for message in replies],
        "unmatched_buyer_message_ids": sorted(buyer_ids - reply_ids),
        "thread_ids": sorted(first_sent),
        "replies": [
            {
                "id": "gmail-reply:" + message["id"],
                "message_id": message["id"],
                "thread_id": message["thread_id"],
                "ts": message["ts"],
                "source_ref": "gmail:" + message["id"],
            }
            for message in replies
        ],
        "scope": "SUPPLIED_MESSAGES_ONLY",
    }
