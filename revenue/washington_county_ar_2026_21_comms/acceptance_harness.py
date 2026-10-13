"""Synthetic, read-only acceptance harness for the TJLabs subcontract seam.

Purpose: demonstrate deterministic testing of the bid's cross-channel continuity,
identity gate, Agency-controlled knowledge version, and read-only property lookup.
It is not a production platform and does not claim Washington County integration.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

ALLOWED_CHANNELS = {"phone", "chat", "email"}
ACCOUNT_FIELDS = {"application_status", "exemption_status", "appeal_status"}
PUBLIC_FIELDS = {"parcel_id", "situs_address", "assessed_value", "filing_deadline"}

class HarnessError(ValueError):
    pass

@dataclass(frozen=True)
class Event:
    event_id: str
    case_id: str
    constituent_id: str
    channel: str
    knowledge_version: str
    action: str
    field: str | None = None
    identity_confirmed: bool = False


def parse_event(obj: dict[str, Any]) -> Event:
    allowed = {"event_id", "case_id", "constituent_id", "channel", "knowledge_version", "action", "field", "identity_confirmed"}
    extra = set(obj) - allowed
    if extra:
        raise HarnessError(f"unknown fields: {sorted(extra)}")
    for key in ("event_id", "case_id", "constituent_id", "channel", "knowledge_version", "action"):
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            raise HarnessError(f"invalid {key}")
    if obj["channel"] not in ALLOWED_CHANNELS:
        raise HarnessError("unsupported channel")
    if type(obj.get("identity_confirmed", False)) is not bool:
        raise HarnessError("identity_confirmed must be bool")
    return Event(**{k: obj.get(k) for k in Event.__dataclass_fields__})


def evaluate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    if set(scenario) != {"schema_version", "knowledge_version", "events"}:
        raise HarnessError("scenario keys must be exact")
    if scenario["schema_version"] != 1:
        raise HarnessError("unsupported schema")
    kv = scenario["knowledge_version"]
    if not isinstance(kv, str) or not kv.strip():
        raise HarnessError("invalid knowledge_version")
    events_raw = scenario["events"]
    if not isinstance(events_raw, list) or not events_raw:
        raise HarnessError("events must be non-empty list")

    seen_ids: set[str] = set()
    case_constituent: dict[str, str] = {}
    channels_by_case: dict[str, set[str]] = {}
    failures: list[str] = []
    lookups = 0

    for raw in events_raw:
        if not isinstance(raw, dict):
            raise HarnessError("event must be object")
        ev = parse_event(raw)
        if ev.event_id in seen_ids:
            failures.append(f"DUPLICATE_EVENT:{ev.event_id}")
            continue
        seen_ids.add(ev.event_id)
        if ev.knowledge_version != kv:
            failures.append(f"KNOWLEDGE_DRIFT:{ev.event_id}")
        prior_constituent = case_constituent.setdefault(ev.case_id, ev.constituent_id)
        if prior_constituent != ev.constituent_id:
            failures.append(f"CASE_CONSTITUENT_DRIFT:{ev.event_id}")
        channels_by_case.setdefault(ev.case_id, set()).add(ev.channel)

        if ev.action == "read_property":
            lookups += 1
            if ev.field not in PUBLIC_FIELDS | ACCOUNT_FIELDS:
                failures.append(f"FIELD_NOT_ALLOWLISTED:{ev.event_id}")
            elif ev.field in ACCOUNT_FIELDS and not ev.identity_confirmed:
                failures.append(f"IDENTITY_REQUIRED:{ev.event_id}")
        elif ev.action in {"create_case", "continue_case", "handoff_live", "send_link"}:
            pass
        else:
            failures.append(f"ACTION_NOT_READ_ONLY:{ev.event_id}")

    cross_channel_cases = sorted(case for case, chans in channels_by_case.items() if len(chans) >= 2)
    result = {
        "schema_version": 1,
        "status": "PASS" if not failures else "HOLD",
        "failure_codes": sorted(failures),
        "event_count": len(events_raw),
        "property_lookup_count": lookups,
        "cross_channel_case_ids": cross_channel_cases,
        "knowledge_version": kv,
        "read_only_enforced": not any("ACTION_NOT_READ_ONLY" in f for f in failures),
    }
    result["receipt_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return result
