#!/usr/bin/env python3
"""Hash-chain creation and verification for retained creative-review events."""
from __future__ import annotations

from typing import Any

from _validation import sha256_json


def _event_hash(
    campaign_id: str,
    ordinal: int,
    event_kind: str,
    payload: dict[str, Any],
    at_utc: str,
    previous_hash: str,
) -> str:
    return sha256_json(
        {
            "campaign_id": campaign_id,
            "ordinal": ordinal,
            "event_kind": event_kind,
            "payload": payload,
            "at_utc": at_utc,
            "previous_hash": previous_hash,
        }
    )


def _verify_event_chain(campaign_id: str, events: list[dict[str, Any]]) -> tuple[bool, str | None]:
    previous = "0" * 64
    for expected_ordinal, event in enumerate(events, 1):
        required = {"ordinal", "event_kind", "payload", "at_utc", "previous_hash", "event_hash"}
        if type(event) is not dict or set(event) != required:
            return False, "AUDIT_EVENT_SHAPE"
        if event["ordinal"] != expected_ordinal:
            return False, "AUDIT_ORDINAL_GAP"
        if event["previous_hash"] != previous:
            return False, "AUDIT_PREVIOUS_HASH_MISMATCH"
        expected = _event_hash(
            campaign_id,
            expected_ordinal,
            event["event_kind"],
            event["payload"],
            event["at_utc"],
            previous,
        )
        if event["event_hash"] != expected:
            return False, "AUDIT_EVENT_HASH_MISMATCH"
        previous = expected
    return True, None
