from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping

INPUT_SCHEMA = "provider-route-authority-input/v1"
RECEIPT_SCHEMA = "provider-route-authority-receipt/v1"
EVIDENCE_TRUST = "CALLER_ASSERTED_UNAUTHENTICATED"

ALLOWED_DECISIONS = {"CANDIDATE_ONE_SEND", "HARD_DNR", "DEAD_ROUTE", "HOLD_UNKNOWN", "INBOUND_ONLY"}
_EVENT_SOURCE = {
    "SLACK_TAKE": "SLACK", "MUSE_CLEAR": "MUSE", "ROUTE_VERIFIED": "PUBLIC_EVIDENCE",
    "PROVIDER_SENT": "PROVIDER", "HARD_BOUNCE": "PROVIDER", "SOFT_BOUNCE": "PROVIDER",
    "PROVIDER_TIMEOUT": "PROVIDER", "HUMAN_REPLY": "MAILBOX", "HUMAN_REJECTION": "MAILBOX",
}
_ROUTE_TYPES = {"EMAIL", "FORM", "DM", "PHONE", "OTHER"}
_ORG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,127}$")
_PURPOSE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


class AuthorityError(ValueError):
    pass


def _reject_float(_: str) -> None:
    raise AuthorityError("floats are not allowed")


def _parse_int(token: str) -> int:
    if len(token.lstrip("-")) > 128:
        raise AuthorityError("integer token too long")
    return int(token)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AuthorityError(f"duplicate key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=_reject_float,
                          parse_int=_parse_int, parse_constant=_reject_float)
    except AuthorityError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise AuthorityError(f"invalid JSON: {exc}") from None


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False) + "\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AuthorityError(f"cannot canonicalize: {exc}") from None


def _map(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuthorityError(f"{where} must be an object")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(obj)
    if actual != expected:
        raise AuthorityError(f"{where} keys mismatch; missing={sorted(expected-actual)} extra={sorted(actual-expected)}")


def _text(value: Any, where: str, *, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise AuthorityError(f"{where} must be non-empty text <= {max_len}")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise AuthorityError(f"{where} must be one line")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise AuthorityError(f"{where} must be Unicode scalar text") from None
    return value


def _org(value: Any, where: str) -> str:
    value = _text(value, where, max_len=128).lower()
    if not _ORG_RE.fullmatch(value):
        raise AuthorityError(f"{where} must be a lowercase slug/domain-like token")
    return value


def _purpose(value: Any, where: str) -> str:
    value = _text(value, where, max_len=128)
    if not _PURPOSE_RE.fullmatch(value):
        raise AuthorityError(f"{where} has invalid token characters")
    return value


def _timestamp(value: Any, where: str) -> str:
    value = _text(value, where, max_len=64)
    parsed_text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(parsed_text)
    except ValueError:
        raise AuthorityError(f"{where} must be ISO-8601") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise AuthorityError(f"{where} must include a timezone")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_key(value: str) -> datetime:
    parsed_text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(parsed_text)


def _route(value: Any, route_type: str, where: str) -> str:
    value = _text(value, where, max_len=512).strip()
    if not value:
        raise AuthorityError(f"{where} must not be blank")
    if route_type == "EMAIL":
        if value.count("@") != 1 or " " in value:
            raise AuthorityError(f"{where} must be an email route")
        local, domain = value.rsplit("@", 1)
        if not local or not domain or "." not in domain:
            raise AuthorityError(f"{where} must be an email route")
        return f"{local.lower()}@{domain.lower()}"
    return value


def _route_type(value: Any, where: str) -> str:
    value = _text(value, where, max_len=16)
    if value not in _ROUTE_TYPES:
        raise AuthorityError(f"{where} invalid")
    return value


def _subject(raw: Any) -> dict[str, str]:
    raw = _map(raw, "subject")
    _exact_keys(raw, {"org", "route_type", "route", "purpose"}, "subject")
    route_type = _route_type(raw["route_type"], "subject.route_type")
    return {
        "org": _org(raw["org"], "subject.org"),
        "route_type": route_type,
        "route": _route(raw["route"], route_type, "subject.route"),
        "purpose": _purpose(raw["purpose"], "subject.purpose"),
    }


def _event(raw: Any, index: int) -> dict[str, str]:
    where = f"events[{index}]"
    raw = _map(raw, where)
    _exact_keys(raw, {"event_id", "kind", "source", "at", "org", "purpose",
                      "route_type", "route", "evidence_ref"}, where)
    event_id = _text(raw["event_id"], f"{where}.event_id", max_len=160)
    if not _EVENT_ID_RE.fullmatch(event_id):
        raise AuthorityError(f"{where}.event_id invalid")
    kind = _text(raw["kind"], f"{where}.kind", max_len=32)
    expected_source = _EVENT_SOURCE.get(kind)
    if expected_source is None:
        raise AuthorityError(f"{where}.kind invalid")
    source = _text(raw["source"], f"{where}.source", max_len=32)
    if source != expected_source:
        raise AuthorityError(f"{where}.source must be {expected_source} for {kind}")
    route_type = _route_type(raw["route_type"], f"{where}.route_type")
    return {
        "event_id": event_id,
        "kind": kind,
        "source": source,
        "at": _timestamp(raw["at"], f"{where}.at"),
        "org": _org(raw["org"], f"{where}.org"),
        "purpose": _purpose(raw["purpose"], f"{where}.purpose"),
        "route_type": route_type,
        "route": _route(raw["route"], route_type, f"{where}.route"),
        "evidence_ref": _text(raw["evidence_ref"], f"{where}.evidence_ref", max_len=512),
    }


def normalize_input(raw: Mapping[str, Any]) -> dict[str, Any]:
    raw = _map(raw, "root")
    _exact_keys(raw, {"schema", "subject", "events"}, "root")
    if raw["schema"] != INPUT_SCHEMA:
        raise AuthorityError(f"schema must be {INPUT_SCHEMA}")
    subject = _subject(raw["subject"])
    events_raw = raw["events"]
    if not isinstance(events_raw, list) or len(events_raw) > 512:
        raise AuthorityError("events must be an array of <=512 events")
    events = [_event(value, i) for i, value in enumerate(events_raw)]
    seen: set[str] = set()
    for event in events:
        if event["event_id"] in seen:
            raise AuthorityError(f"duplicate event_id: {event['event_id']}")
        seen.add(event["event_id"])
    events.sort(key=lambda item: (_timestamp_key(item["at"]), item["event_id"], item["kind"],
                                  item["org"], item["purpose"], item["route_type"], item["route"]))
    return {"schema": INPUT_SCHEMA, "subject": subject, "events": events}


def _same_org(event: Mapping[str, str], subject: Mapping[str, str]) -> bool:
    return event["org"] == subject["org"]


def _same_route(event: Mapping[str, str], subject: Mapping[str, str]) -> bool:
    return (_same_org(event, subject) and event["route_type"] == subject["route_type"]
            and event["route"] == subject["route"])


def _exact_subject(event: Mapping[str, str], subject: Mapping[str, str]) -> bool:
    return _same_route(event, subject) and event["purpose"] == subject["purpose"]


def _latest(events: list[dict[str, str]], kind: str) -> dict[str, str] | None:
    matches = [event for event in events if event["kind"] == kind]
    return matches[-1] if matches else None


def _strictly_after(left: dict[str, str] | None, right: dict[str, str] | None) -> bool:
    if left is None or right is None:
        return False
    return _timestamp_key(left["at"]) > _timestamp_key(right["at"])


def evaluate(normalized: Mapping[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    subject = normalized["subject"]
    events: list[dict[str, str]] = list(normalized["events"])
    same_org = [event for event in events if _same_org(event, subject)]
    same_route = [event for event in same_org if _same_route(event, subject)]
    exact = [event for event in same_route if _exact_subject(event, subject)]

    human = [event for event in same_org if event["kind"] in {"HUMAN_REPLY", "HUMAN_REJECTION"}]
    route_hard = [event for event in same_route if event["kind"] == "HARD_BOUNCE"]
    route_sent = [event for event in same_route if event["kind"] == "PROVIDER_SENT"]
    exact_sent = [event for event in exact if event["kind"] == "PROVIDER_SENT"]
    route_uncertain = [event for event in same_route if event["kind"] in {"SOFT_BOUNCE", "PROVIDER_TIMEOUT"}]
    org_hard_routes = {(event["route_type"], event["route"]) for event in same_org if event["kind"] == "HARD_BOUNCE"}
    org_sent_routes = {(event["route_type"], event["route"]) for event in same_org if event["kind"] == "PROVIDER_SENT"}

    provider_truth = {
        "human_event_ids": [event["event_id"] for event in human],
        "same_route_sent_event_ids": [event["event_id"] for event in route_sent],
        "exact_subject_sent_event_ids": [event["event_id"] for event in exact_sent],
        "same_route_hard_bounce_event_ids": [event["event_id"] for event in route_hard],
        "same_route_uncertain_event_ids": [event["event_id"] for event in route_uncertain],
        "org_hard_failed_routes": [{"route_type": rt, "route": route} for rt, route in sorted(org_hard_routes)],
        "org_provider_sent_routes": [{"route_type": rt, "route": route} for rt, route in sorted(org_sent_routes)],
    }

    if human:
        return "INBOUND_ONLY", ["GENUINE_HUMAN_EVENT_PRESENT", "NO_AUTOMATED_FOLLOWUP_AUTHORITY"], provider_truth
    if route_hard:
        return "DEAD_ROUTE", ["ROUTE_HARD_BOUNCE", "BOUNCE_IS_NOT_PERMISSION_TO_ROUTE_AROUND"], provider_truth
    if len(org_hard_routes) >= 2:
        return "HOLD_UNKNOWN", ["ORG_MULTI_ROUTE_HARD_FAILURE", "ROUTE_SPRAY_GUARD"], provider_truth
    if route_uncertain:
        latest_uncertain = route_uncertain[-1]
        latest_sent = route_sent[-1] if route_sent else None
        if latest_sent is None or _timestamp_key(latest_uncertain["at"]) >= _timestamp_key(latest_sent["at"]):
            return "HOLD_UNKNOWN", ["ROUTE_DELIVERY_UNCERTAIN", "NO_RETRY_AUTHORITY"], provider_truth
    if exact_sent:
        return "HARD_DNR", ["EXACT_SUBJECT_PROVIDER_SENT", "WAIT_FOR_GENUINE_EVENT"], provider_truth
    if route_sent:
        return "HOLD_UNKNOWN", ["ROUTE_ALREADY_CONTACTED_OTHER_PURPOSE", "NO_DUPLICATE_ROUTE_AUTHORITY"], provider_truth
    if org_sent_routes:
        return "HOLD_UNKNOWN", ["ORG_ALREADY_CONTACTED_OTHER_ROUTE", "NO_ROUTE_FANOUT_AUTHORITY"], provider_truth

    take = _latest(exact, "SLACK_TAKE")
    muse = _latest(exact, "MUSE_CLEAR")
    verified = _latest(exact, "ROUTE_VERIFIED")
    if take is None:
        return "HOLD_UNKNOWN", ["NO_CURRENT_COORDINATION_TAKE"], provider_truth
    if muse is None or not _strictly_after(muse, take):
        return "HOLD_UNKNOWN", ["NO_POST_TAKE_MUSE_CLEAR"], provider_truth
    if verified is None or not _strictly_after(verified, take):
        return "HOLD_UNKNOWN", ["NO_POST_TAKE_ROUTE_VERIFICATION"], provider_truth
    return "CANDIDATE_ONE_SEND", [
        "POST_TAKE_MUSE_CLEAR",
        "POST_TAKE_ROUTE_VERIFIED",
        "NO_PROVIDER_OR_HUMAN_HOLD",
        "CALLER_EVIDENCE_UNAUTHENTICATED",
        "LIVE_SLACK_MUSE_PROVIDER_RECENSUS_REQUIRED",
    ], provider_truth


def compile_authority(raw: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_input(raw)
    decision, reasons, provider_truth = evaluate(normalized)
    digest = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
    return {
        "schema": RECEIPT_SCHEMA,
        "subject": normalized["subject"],
        "decision": decision,
        "reasons": reasons,
        "provider_truth": provider_truth,
        "event_count": len(normalized["events"]),
        "evidence_digest_sha256": digest,
        "evidence_trust": EVIDENCE_TRUST,
        "authority": {
            "external_send_authorized": False,
            "muse_request_authorized": False,
            "provider_mutation_authorized": False,
            "payment_mutation_authorized": False,
            "revenue_recognition_authorized": False,
        },
    }


def verify_authority(raw: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    expected = compile_authority(raw)
    if canonical_json(expected) != canonical_json(receipt):
        raise AuthorityError("receipt does not exactly match deterministic recomputation")
