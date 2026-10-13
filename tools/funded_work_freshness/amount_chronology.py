"""Chronology-safe authoritative reward amount resolution.

The current issue snapshot and trusted comments are independent authority events.
They must be ordered on one validated timeline; source type does not silently win.
Conflicting amount statements at the same instant fail closed.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from evaluation import (
    _commercial_amount_event,
    funding_authority,
    parse_timestamp,
    trusted_comment,
)


def _authority_events(
    issue: Mapping[str, Any], comments: Sequence[Mapping[str, Any]]
) -> list[tuple[datetime | None, int, int, str]]:
    """Return issue/comment authority events without inventing missing chronology."""

    events: list[tuple[datetime | None, int, int, str]] = []
    issue_user = issue.get("user") if isinstance(issue.get("user"), Mapping) else {}
    if funding_authority(issue_user, issue.get("author_association")):
        events.append(
            (
                parse_timestamp(issue.get("updated_at"))
                or parse_timestamp(issue.get("created_at")),
                0,
                0,
                "\n".join(
                    (str(issue.get("title") or ""), str(issue.get("body") or ""))
                ),
            )
        )

    for index, comment in enumerate(comments):
        if not trusted_comment(comment):
            continue
        events.append(
            (
                parse_timestamp(comment.get("updated_at"))
                or parse_timestamp(comment.get("created_at")),
                1,
                index,
                str(comment.get("body") or ""),
            )
        )
    return events


def authoritative_amount_state(
    issue: Mapping[str, Any],
    comments: Sequence[Mapping[str, Any]],
    advertised_amount: str,
    advertised_currency: str,
) -> dict[str, str | bool | None]:
    """Resolve the latest trusted amount across issue edits and comments.

    Amount-bearing authority without a valid timestamp is ambiguous because it
    cannot be positioned safely. At one timestamp, identical resolved statements
    agree; conflicting resolved values or any ambiguous statement fail closed.
    A later non-amount event does not erase the last amount authority.
    """

    parsed_events: list[tuple[datetime, int, int, dict[str, str | None]]] = []
    for stamp, source_rank, index, text in _authority_events(issue, comments):
        event = _commercial_amount_event(text)
        if event["status"] == "none":
            continue
        if stamp is None:
            return {
                "status": "ambiguous",
                "currency": None,
                "amount": None,
                "matches_advertised": False,
            }
        parsed_events.append((stamp, source_rank, index, event))

    status = "missing"
    current_currency: str | None = None
    current_amount: str | None = None

    cursor = 0
    parsed_events.sort(key=lambda row: (row[0], row[1], row[2]))
    while cursor < len(parsed_events):
        stamp = parsed_events[cursor][0]
        bucket: list[dict[str, str | None]] = []
        while cursor < len(parsed_events) and parsed_events[cursor][0] == stamp:
            bucket.append(parsed_events[cursor][3])
            cursor += 1

        if any(event["status"] == "ambiguous" for event in bucket):
            status = "ambiguous"
            current_currency = None
            current_amount = None
            continue

        resolved = {
            (str(event["currency"]), str(event["amount"]))
            for event in bucket
            if event["status"] == "resolved"
        }
        if len(resolved) > 1:
            status = "ambiguous"
            current_currency = None
            current_amount = None
        elif len(resolved) == 1:
            status = "resolved"
            current_currency, current_amount = next(iter(resolved))

    matches = (
        status == "resolved"
        and current_currency == advertised_currency
        and current_amount is not None
        and Decimal(current_amount) == Decimal(advertised_amount)
    )
    return {
        "status": status,
        "currency": current_currency,
        "amount": current_amount,
        "matches_advertised": matches,
    }
